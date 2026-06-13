"""
fetch_git.py — local-git extraction (no network, no rate limits).

Produces data/raw/git.json with everything the rubric needs from history:
  - commits      : per-commit author/email/date/co-authors + per-file ins/del/weight
                   (90d scoring window, non-merge, hygiene-filtered files)
  - file_hotness : distinct team commits touching each file in the 365d lookback
  - ownership    : per file at HEAD -> surviving lines per author (blame), restricted
                   to files touched in the last 365d (per locked decision)
  - survival     : per author -> surviving lines at HEAD whose introducing commit
                   falls inside the 90d window (numerator for survival_rate)

Notes
-----
* Relies on the repo .mailmap (git applies it to log/blame automatically) plus
  downstream IdentityResolver for the rest.
* Clone is shallow-since 365d, so blame lines older than the boundary are
  'boundary' lines and are skipped -> ownership reflects the last 365d of
  authorship of surviving lines. This is intentional and recorded in meta.
* Blame is parallelised across CPUs; only hygiene-passing files touched in the
  lookback are blamed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone

import hygiene

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
US = "\x1f"  # unit separator for --format fields

REPO_DIR = ""  # set in main(); module-global so blame workers inherit it via initializer


def _run(args: list[str], cwd: str) -> str:
    return subprocess.run(
        args, cwd=cwd, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout


def iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


def normalize_path(path: str) -> str:
    """Resolve a numstat rename path ('a => b' or 'pre/{a => b}/post') to the new path."""
    if "=>" not in path:
        return path
    if "{" in path and "}" in path:
        pre, rest = path.split("{", 1)
        mid, post = rest.split("}", 1)
        new = mid.split("=>")[-1].strip()
        return (pre + new + post).replace("//", "/")
    return path.split("=>")[-1].strip()


# --------------------------------------------------------------------------- #
# Commits (90d window)
# --------------------------------------------------------------------------- #

def extract_commits(repo: str, since: str) -> list[dict]:
    """Two cheap passes over the 90d log: metadata+trailers, then numstat."""
    # Pass 1: one line per commit with subject (for PR-number bridge) + co-author trailers.
    fmt = US.join(["%H", "%an", "%ae", "%cn", "%ce", "%cI", "%s",
                   "%(trailers:key=Co-authored-by,valueonly,separator=%x1e)"])
    meta_out = _run(
        ["git", "log", "--no-merges", f"--since={since}", f"--pretty=format:{fmt}"],
        repo,
    )
    commits: dict[str, dict] = {}
    order: list[str] = []
    for line in meta_out.splitlines():
        if not line:
            continue
        parts = line.split(US)
        if len(parts) < 8:
            continue
        sha, an, ae, cn, ce, cdate, subject, trailers = parts[:8]
        pr_m = re.search(r"\(#(\d+)\)\s*$", subject)
        pr_number = int(pr_m.group(1)) if pr_m else None
        coauthors = []
        for t in trailers.split("\x1e"):
            t = t.strip()
            if not t:
                continue
            m = re.match(r"^(.*?)\s*<(.+?)>$", t)
            if m:
                coauthors.append({"name": m.group(1).strip(), "email": m.group(2).strip().lower()})
            elif "@" in t:
                coauthors.append({"name": "", "email": t.strip().lower()})
        commits[sha] = {
            "sha": sha, "author_name": an, "author_email": ae.lower(),
            "committer_name": cn, "committer_email": ce.lower(),
            "date": cdate, "subject": subject, "pr_number": pr_number,
            "coauthors": coauthors, "files": [],
        }
        order.append(sha)

    # Pass 2: numstat keyed by sha. Format emits a bare sha line, then numstat rows.
    # Rename detection ON (-M): pure moves report 0/0 and add no churn — this is
    # what stops directory-rename commits from inflating authorship.
    num_out = _run(
        ["git", "log", "--no-merges", f"--since={since}",
         "--numstat", "-M", "--pretty=format:%H"],
        repo,
    )
    cur = None
    for line in num_out.splitlines():
        if SHA_RE.match(line):
            cur = line
            continue
        if cur is None or not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) != 3:
            continue
        ins_s, del_s, path = cols
        if ins_s == "-" or del_s == "-":  # binary
            continue
        path = normalize_path(path)
        if hygiene.is_excluded_file(path):
            continue
        c = commits.get(cur)
        if c is None:
            continue
        ins, dele = int(ins_s), int(del_s)
        c["files"].append({
            "path": path, "ins": ins, "del": dele,
            "weight": hygiene.dir_weight(path),
        })
    return [commits[s] for s in order]


# --------------------------------------------------------------------------- #
# File hotness (365d lookback) — distinct commits touching each file
# --------------------------------------------------------------------------- #

def extract_hotness(repo: str, since: str) -> dict[str, int]:
    out = _run(
        ["git", "log", "--no-merges", f"--since={since}",
         "--name-only", "--pretty=format:%H"],
        repo,
    )
    hotness: dict[str, set[str]] = {}
    cur = None
    for line in out.splitlines():
        if SHA_RE.match(line):
            cur = line
            continue
        path = line.strip()
        if not path or cur is None:
            continue
        if hygiene.is_excluded_file(path):
            continue
        hotness.setdefault(path, set()).add(cur)
    return {p: len(s) for p, s in hotness.items()}


# --------------------------------------------------------------------------- #
# Blame (ownership + survival) — parallel per file
# --------------------------------------------------------------------------- #

def _blame_init(repo: str) -> None:
    global REPO_DIR
    REPO_DIR = repo


def _blame_file(args: tuple[str, float]) -> dict | None:
    """Blame one file at HEAD; return per-author surviving lines + window survivors."""
    path, window_epoch = args
    try:
        # errors='replace': some tracked files contain non-UTF-8 bytes; we only
        # need the porcelain metadata + line counts, not faithful content.
        out = subprocess.run(
            ["git", "blame", "-w", "-M", "--line-porcelain", "HEAD", "--", path],
            cwd=REPO_DIR, check=True, text=True, errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        ).stdout
    except Exception:
        # bad path, binary, decode edge case — skip this file, never abort batch
        return None

    shares: dict[str, int] = {}
    window: dict[str, int] = {}
    total = 0
    cur_email = None
    cur_time = 0
    boundary = False
    try:
        for line in out.splitlines():
            if line.startswith("author-mail "):
                cur_email = line[12:].strip().strip("<>").lower()
            elif line.startswith("author-time "):
                cur_time = int(line[12:].strip() or 0)
            elif line == "boundary":
                boundary = True
            elif line.startswith("\t"):
                # the actual source line terminates one porcelain record
                if cur_email and not boundary:
                    shares[cur_email] = shares.get(cur_email, 0) + 1
                    total += 1
                    if cur_time >= window_epoch:
                        window[cur_email] = window.get(cur_email, 0) + 1
                cur_email, cur_time, boundary = None, 0, False
    except Exception:
        return None
    if total == 0:
        return None
    primary = max(shares, key=shares.get)
    return {
        "path": path, "total": total, "primary": primary,
        "shares": shares, "window": window,
    }


def extract_blame(repo: str, files: list[str], window_since: str, workers: int,
                  max_files: int | None) -> tuple[dict, dict]:
    window_epoch = datetime.fromisoformat(window_since).replace(
        tzinfo=timezone.utc).timestamp()
    if max_files:
        files = files[:max_files]
    n = len(files)
    print(f"  blaming {n} files across {workers} workers...", flush=True)

    ownership: dict[str, dict] = {}
    survival: dict[str, int] = {}
    t0 = time.time()
    done = 0
    payload = [(f, window_epoch) for f in files]
    with ProcessPoolExecutor(max_workers=workers, initializer=_blame_init,
                             initargs=(repo,)) as ex:
        for res in ex.map(_blame_file, payload, chunksize=16):
            done += 1
            if done % 1000 == 0:
                rate = done / max(time.time() - t0, 1e-6)
                print(f"    {done}/{n}  ({rate:.0f} files/s)", flush=True)
            if res is None:
                continue
            ownership[res["path"]] = {
                "primary": res["primary"], "total": res["total"],
                "shares": res["shares"],
            }
            for email, cnt in res["window"].items():
                survival[email] = survival.get(email, 0) + cnt
    print(f"  blame done in {time.time() - t0:.1f}s "
          f"({len(ownership)} files attributed)", flush=True)
    return ownership, survival


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="path to cloned repo")
    ap.add_argument("--out", default="data/raw/git.json")
    ap.add_argument("--window-days", type=int, default=90)
    ap.add_argument("--lookback-days", type=int, default=365)
    ap.add_argument("--workers", type=int, default=max(os.cpu_count() or 4, 4))
    ap.add_argument("--max-blame-files", type=int, default=None,
                    help="safety cap on number of files to blame")
    ap.add_argument("--skip-blame", action="store_true",
                    help="extract commits+hotness only (fast preview)")
    ap.add_argument("--reuse-blame", default=None,
                    help="path to an existing git.json: reuse its ownership/survival "
                         "(blame is unaffected by churn/hygiene fixes) and only "
                         "recompute commits+hotness")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    window_since = iso_days_ago(args.window_days)
    lookback_since = iso_days_ago(args.lookback_days)
    head = _run(["git", "rev-parse", "HEAD"], repo).strip()
    print(f"repo={repo}\n window_since={window_since} lookback_since={lookback_since}\n head={head}")

    t = time.time()
    print("extracting commits (90d)...", flush=True)
    commits = extract_commits(repo, window_since)
    print(f"  {len(commits)} commits in {time.time()-t:.1f}s")

    t = time.time()
    print("extracting file hotness (365d)...", flush=True)
    hotness = extract_hotness(repo, lookback_since)
    print(f"  {len(hotness)} files in {time.time()-t:.1f}s")

    ownership: dict = {}
    survival: dict = {}
    if args.reuse_blame:
        with open(args.reuse_blame) as f:
            prev = json.load(f)
        ownership = prev.get("ownership", {})
        survival = prev.get("survival_window_lines", {})
        print(f"reused blame from {args.reuse_blame}: "
              f"{len(ownership)} files, {len(survival)} authors")
    elif not args.skip_blame:
        candidate_files = sorted(hotness.keys())  # already hygiene-filtered, 365d-touched
        ownership, survival = extract_blame(
            repo, candidate_files, window_since, args.workers, args.max_blame_files)

    out = {
        "head": head,
        "window_since": window_since,
        "lookback_since": lookback_since,
        "window_days": args.window_days,
        "lookback_days": args.lookback_days,
        "commits": commits,
        "file_hotness": hotness,
        "ownership": ownership,
        "survival_window_lines": survival,
        "blame_skipped": args.skip_blame,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f)
    sz = os.path.getsize(args.out) / 1e6
    print(f"wrote {args.out} ({sz:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
