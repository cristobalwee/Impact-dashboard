"""
score.py — compute the 5-pillar impact composite and emit engineers.json.

Reads data/raw/git.json + data/raw/github.json, merges identities, computes raw
metrics per engineer, percentile-normalizes within the active cohort, blends
into pillars, and writes app/public/engineers.json per the data contract.

Per-pillar scores are stored (not just composite) so the UI can reweight purely
client-side: composite = Σ(pillar × weight) / Σweight.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

import hygiene

DEFAULT_WEIGHTS = {
    "authorship": 25, "collaboration": 25, "ownership": 20,
    "consistency": 15, "influence": 15,
}

NOREPLY_RE = re.compile(r"^(?:\d+\+)?([A-Za-z0-9-]+)@users\.noreply\.github\.com$")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def iso_week(dt_str: str) -> str:
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def percentile_ranks(values: dict[str, float]) -> dict[str, float]:
    """
    Rank-based percentile (0–100) within the cohort, robust to outliers.
    Uses average-rank for ties: pct = (#below + 0.5·#equal) / N · 100.
    A cohort of all-zero on a metric maps everyone to 0 (no false signal).
    """
    ids = list(values)
    n = len(ids)
    if n == 0:
        return {}
    out = {}
    vals = list(values.values())
    for i in ids:
        v = values[i]
        below = sum(1 for x in vals if x < v)
        equal = sum(1 for x in vals if x == v)
        out[i] = round((below + 0.5 * equal) / n * 100, 2)
    # If everyone is identical (incl. all-zero), rank gives 50 for all; force 0
    # only when the metric carries no information (all zero).
    if all(v == 0 for v in vals):
        return {i: 0.0 for i in ids}
    return out


# --------------------------------------------------------------------------- #
# Identity resolution
# --------------------------------------------------------------------------- #

def build_resolver(git: dict, gh: dict):
    r = hygiene.IdentityResolver()

    def feed_email(name, email):
        if not email:
            return
        r.observe(name=name, email=email)
        m = NOREPLY_RE.match(email)
        if m:  # bridge git noreply email -> github login deterministically
            r.observe(login=m.group(1), email=email)

    for c in git["commits"]:
        feed_email(c["author_name"], c["author_email"])
        for co in c["coauthors"]:
            feed_email(co.get("name", ""), co["email"])

    for login, info in gh.get("users", {}).items():
        r.observe(login=login, name=info.get("name", ""),
                  avatar_url=info.get("avatar_url", ""))

    # Strongest bridge: squash-merge subject carries (#PR); union the commit
    # author email with that PR's known GitHub author login.
    pr_author = {pr["number"]: pr["author"] for pr in gh.get("pull_requests", [])}
    for c in git["commits"]:
        prn = c.get("pr_number")
        if prn and pr_author.get(prn):
            r.observe(login=pr_author[prn], email=c["author_email"])

    return r


# --------------------------------------------------------------------------- #
# Metric computation
# --------------------------------------------------------------------------- #

def compute(git: dict, gh: dict, weights: dict) -> dict:
    r = build_resolver(git, gh)

    def cid_email(email):
        return r.canonical_for_email(email) if email else None

    def cid_login(login):
        return r.canonical_for_login(login) if login else None

    # Accumulators keyed by canonical id (raw union-find root).
    commits_n = defaultdict(int)
    weighted_churn = defaultdict(float)
    effective_churn = defaultdict(int)
    window_insertions = defaultdict(int)
    merged_prs = defaultdict(int)
    reviews_sub = defaultdict(int)
    reviewed_authors = defaultdict(set)
    review_comments = defaultdict(int)
    issue_comments = defaultdict(int)
    coauthor_partners = defaultdict(set)
    active_weeks = defaultdict(set)
    week_commits = defaultdict(lambda: defaultdict(int))
    week_reviews = defaultdict(lambda: defaultdict(int))
    bot_ids = set()

    def mark_bot(cid, name="", login="", email=""):
        if cid and hygiene.is_bot(login=login, name=name, email=email):
            bot_ids.add(cid)

    # ---- git: commits, churn, co-authors, consistency ----
    for c in git["commits"]:
        cid = cid_email(c["author_email"])
        mark_bot(cid, name=c["author_name"], email=c["author_email"])
        if not cid:
            continue
        commits_n[cid] += 1
        wk = iso_week(c["date"])
        active_weeks[cid].add(wk)
        week_commits[cid][wk] += 1
        for f in c["files"]:
            ec = f["ins"] + f["del"]
            effective_churn[cid] += ec
            weighted_churn[cid] += ec * f["weight"]
            window_insertions[cid] += f["ins"]
        # co-authorship is bidirectional
        partners = [cid] + [cid_email(co["email"]) for co in c["coauthors"]]
        partners = [p for p in partners if p]
        for a in partners:
            for b in partners:
                if a != b:
                    coauthor_partners[a].add(b)

    # ---- survival numerator (blame lines authored in-window, surviving HEAD) ----
    surviving_window = defaultdict(int)
    for email, n in git.get("survival_window_lines", {}).items():
        cid = cid_email(email)
        if cid:
            surviving_window[cid] += n

    # ---- ownership / criticality ----
    hotness = git.get("file_hotness", {})
    ownership_raw = defaultdict(float)
    bus_factor_raw = defaultdict(float)
    owned_files = defaultdict(int)
    owned_critical = defaultdict(int)
    crit_values = sorted(hotness.values())
    crit_median = crit_values[len(crit_values) // 2] if crit_values else 0
    for path, o in git.get("ownership", {}).items():
        total = o["total"]
        if total <= 0:
            continue
        crit = hotness.get(path, 0)
        # roll shares up to canonical ids
        cshares = defaultdict(int)
        for email, lines in o["shares"].items():
            cid = cid_email(email)
            if cid:
                cshares[cid] += lines
        if not cshares:
            continue
        prim = max(cshares, key=cshares.get)
        share = cshares[prim] / total
        if share >= 0.5:
            owned_files[prim] += 1
            ownership_raw[prim] += share * crit
            if crit >= max(crit_median, 1):
                owned_critical[prim] += 1
        if share >= 0.8:
            bus_factor_raw[prim] += crit

    # ---- github: PRs, reviews, comments, consistency ----
    window_start = datetime.fromisoformat(gh["window_start"].replace("Z", "+00:00"))

    def in_window(ts):
        if not ts:
            return False
        return datetime.fromisoformat(ts.replace("Z", "+00:00")) >= window_start

    for pr in gh.get("pull_requests", []):
        cid = cid_login(pr["author"])
        mark_bot(cid, login=pr["author"])
        if cid and pr.get("mergedAt") and in_window(pr["mergedAt"]):
            merged_prs[cid] += 1
            active_weeks[cid].add(iso_week(pr["mergedAt"]))

    for prnum, rvs in gh.get("reviews", {}).items():
        for rv in rvs:
            cid = cid_login(rv["login"])
            mark_bot(cid, login=rv["login"])
            if not cid or not in_window(rv.get("submittedAt")):
                continue
            substantive = (rv["state"] == "CHANGES_REQUESTED"
                           or (rv["state"] in ("APPROVED", "COMMENTED")
                               and rv["body_len"] > 0))
            if substantive:
                reviews_sub[cid] += 1
            review_comments[cid] += rv.get("comment_count", 0)
            pa = cid_login(rv["pr_author"])
            if pa and pa != cid:
                reviewed_authors[cid].add(pa)
            wk = iso_week(rv["submittedAt"])
            active_weeks[cid].add(wk)
            week_reviews[cid][wk] += 1

    for prnum, ics in gh.get("issue_comments", {}).items():
        for ic in ics:
            cid = cid_login(ic["login"])
            mark_bot(cid, login=ic["login"])
            if cid and in_window(ic.get("createdAt")):
                issue_comments[cid] += 1

    # ---- consistency raw (recency-weighted active weeks) ----
    all_weeks = sorted({w for s in active_weeks.values() for w in s})
    week_index = {w: i for i, w in enumerate(all_weeks)}
    total_weeks = max(len(all_weeks), 1)
    consistency_raw = {}
    for cid, weeks in active_weeks.items():
        capped = sorted(weeks)[-13:]  # cap at 13 weeks, keep most recent
        s = 0.0
        for w in capped:
            idx = week_index[w]
            s += 1 + (idx / total_weeks) * 0.5
        consistency_raw[cid] = s

    # ---- influence graph (reviews + co-authorship), weighted degree ----
    edge_w = defaultdict(float)  # (a,b) directed
    for prnum, rvs in gh.get("reviews", {}).items():
        for rv in rvs:
            a, b = cid_login(rv["login"]), cid_login(rv["pr_author"])
            if a and b and a != b and in_window(rv.get("submittedAt")):
                edge_w[(a, b)] += 1
    for c in git["commits"]:
        a = cid_email(c["author_email"])
        for co in c["coauthors"]:
            b = cid_email(co["email"])
            if a and b and a != b:
                edge_w[(a, b)] += 1
                edge_w[(b, a)] += 1

    centrality = _centrality(edge_w)

    # --------------------------------------------------------------------- #
    # Cohort selection
    # --------------------------------------------------------------------- #
    all_ids = (set(commits_n) | set(merged_prs) | set(reviews_sub)
               | set(reviewed_authors) | set(ownership_raw)) - bot_ids

    def qualifies(cid, ct, rt, pt):
        return (commits_n[cid] >= ct or
                (reviews_sub[cid] + len(reviewed_authors[cid])) >= rt or
                merged_prs[cid] >= pt)

    cohort = [i for i in all_ids if qualifies(i, 3, 3, 2)]
    threshold_note = "commits≥3 OR reviews≥3 OR merged_prs≥2"
    if len(cohort) < 8:
        cohort = [i for i in all_ids if qualifies(i, 2, 2, 2)]
        threshold_note = "LOWERED to commits≥2 OR reviews≥2 OR merged_prs≥2 (thin cohort)"

    # --------------------------------------------------------------------- #
    # survival_rate + authored_raw
    # --------------------------------------------------------------------- #
    survival_rate = {}
    authored_raw = {}
    for cid in cohort:
        denom = window_insertions[cid]
        sr = min(1.0, surviving_window[cid] / denom) if denom > 0 else 0.0
        survival_rate[cid] = sr
        authored_raw[cid] = weighted_churn[cid] * (0.5 + 0.5 * sr)

    discussion = {cid: review_comments[cid] + issue_comments[cid] for cid in cohort}

    # --------------------------------------------------------------------- #
    # Percentile-normalize each component within cohort, blend into pillars
    # --------------------------------------------------------------------- #
    def pr_of(d):
        return percentile_ranks({c: float(d.get(c, 0)) for c in cohort})

    p_authored = pr_of(authored_raw)
    p_mergedpr = pr_of(merged_prs)
    p_rev_sub = pr_of(reviews_sub)
    p_distinct = pr_of({c: len(reviewed_authors[c]) for c in cohort})
    p_disc = pr_of(discussion)
    p_coauth = pr_of({c: len(coauthor_partners[c]) for c in cohort})
    p_own = pr_of(ownership_raw)
    p_bus = pr_of(bus_factor_raw)
    p_cons = pr_of(consistency_raw)
    p_infl = pr_of(centrality)

    engineers = []
    display = _display_info(r, gh, cohort)

    for cid in cohort:
        pillars = {
            "authorship": round(0.7 * p_authored[cid] + 0.3 * p_mergedpr[cid], 2),
            "collaboration": round(0.4 * p_rev_sub[cid] + 0.3 * p_distinct[cid]
                                   + 0.2 * p_disc[cid] + 0.1 * p_coauth[cid], 2),
            "ownership": round(0.7 * p_own[cid] + 0.3 * p_bus[cid], 2),
            "consistency": round(p_cons[cid], 2),
            "influence": round(p_infl[cid], 2),
        }
        composite = round(
            sum(pillars[k] * weights[k] for k in weights) / sum(weights.values()), 2)

        stats = {
            "merged_prs": merged_prs[cid],
            "reviews_substantive": reviews_sub[cid],
            "distinct_reviewed": len(reviewed_authors[cid]),
            "effective_churn": effective_churn[cid],
            "survival_rate": round(survival_rate[cid], 3),
            "owned_critical_files": owned_critical[cid],
            "active_weeks": len([w for w in active_weeks[cid]][:13]) if active_weeks[cid] else 0,
            "discussion": discussion[cid],
            "coauthors": len(coauthor_partners[cid]),
            "commits": commits_n[cid],
        }
        di = display.get(cid, {})
        # canonical id: prefer login, else email/root with the internal prefix stripped
        friendly_id = di.get("login") or re.sub(r"^(login|email):", "", cid)
        engineers.append({
            "id": friendly_id,
            "name": di.get("name", "") or di.get("login", "") or friendly_id,
            "login": di.get("login", ""),
            "avatar_url": di.get("avatar_url", ""),
            "composite": composite,
            "pillars": pillars,
            "stats": stats,
            "evidence": _evidence(stats, pillars, di),
            "sparkline": _sparkline(all_weeks, week_commits[cid], week_reviews[cid]),
        })

    engineers.sort(key=lambda e: e["composite"], reverse=True)
    for i, e in enumerate(engineers, 1):
        e["rank"] = i

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": gh.get("repo", "PostHog/posthog"),
        "window_days": git["window_days"],
        "ownership_lookback_days": git["lookback_days"],
        "cohort_size": len(cohort),
        "cohort_threshold": threshold_note,
        "head": git["head"],
        "weights": weights,
        "notes": [
            "Ownership reflects surviving lines authored within the 365d lookback; "
            "lines older than the shallow-clone boundary are not attributed.",
            f"Identity bridge: git-email↔github-login via {len(_pr_bridge_count(git, gh))} "
            "squash-PR matches + GitHub noreply emails.",
        ],
    }
    return {"meta": meta, "engineers": engineers}


def _pr_bridge_count(git, gh):
    pr_author = {pr["number"]: pr["author"] for pr in gh.get("pull_requests", [])}
    return [c for c in git["commits"] if c.get("pr_number") in pr_author]


def _centrality(edge_w: dict) -> dict[str, float]:
    try:
        import networkx as nx
        g = nx.DiGraph()
        for (a, b), w in edge_w.items():
            g.add_edge(a, b, weight=w)
        if g.number_of_nodes() > 2:
            bc = nx.betweenness_centrality(g, weight="weight", normalized=True)
            # scale to a comparable magnitude; percentile makes absolute scale moot
            return {n: v for n, v in bc.items()}
    except Exception:
        pass
    # fallback: weighted degree (in + out)
    deg = defaultdict(float)
    for (a, b), w in edge_w.items():
        deg[a] += w
        deg[b] += w
    return dict(deg)


def _display_info(r, gh, cohort):
    """Resolve a friendly name/login/avatar for each canonical id."""
    idents = r.identities()
    # idents keyed by chosen canonical id; but our cohort ids are union-find roots.
    # Map every email/login back to its root, then attach the richest attrs.
    out = {}
    users = gh.get("users", {})
    for cid in cohort:
        out[cid] = {"name": "", "login": "", "avatar_url": ""}
    # login-based attrs (best source of name+avatar)
    for login, info in users.items():
        root = r.canonical_for_login(login)
        if root in out:
            if not out[root]["login"]:
                out[root]["login"] = login
            if info.get("name") and not out[root]["name"]:
                out[root]["name"] = info["name"]
            if info.get("avatar_url") and not out[root]["avatar_url"]:
                out[root]["avatar_url"] = info["avatar_url"]
    return out


def _evidence(stats, pillars, di) -> list[str]:
    ev = []
    # lead with the strongest pillar
    top = max(pillars, key=pillars.get)
    label = {
        "authorship": "Authorship", "collaboration": "Collaboration & leverage",
        "ownership": "Ownership & criticality", "consistency": "Consistency",
        "influence": "Influence / centrality",
    }[top]
    ev.append(f"Strongest on {label} ({pillars[top]:.0f}th percentile in cohort).")
    if stats["effective_churn"]:
        ev.append(
            f"Wrote {stats['effective_churn']:,} lines of meaningful change "
            f"with {stats['survival_rate']*100:.0f}% still surviving at HEAD.")
    if stats["reviews_substantive"]:
        ev.append(
            f"Left {stats['reviews_substantive']} substantive reviews across "
            f"{stats['distinct_reviewed']} distinct PR authors.")
    if stats["owned_critical_files"]:
        ev.append(
            f"Primary owner of {stats['owned_critical_files']} hot, "
            "load-bearing files.")
    if stats["merged_prs"]:
        ev.append(f"Merged {stats['merged_prs']} PRs in the window.")
    if stats["active_weeks"]:
        ev.append(f"Active in {stats['active_weeks']} of the last 13 weeks.")
    return ev[:4] if len(ev) >= 2 else ev


def _sparkline(all_weeks, wk_commits, wk_reviews) -> list[dict]:
    weeks = all_weeks[-13:]
    return [{"week": w, "commits": wk_commits.get(w, 0),
             "reviews": wk_reviews.get(w, 0)} for w in weeks]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--git", default="data/raw/git.json")
    ap.add_argument("--github", default="data/raw/github.json")
    ap.add_argument("--out", default="app/public/engineers.json")
    args = ap.parse_args()

    with open(args.git) as f:
        git = json.load(f)
    if os.path.exists(args.github):
        with open(args.github) as f:
            gh = json.load(f)
    else:
        print("WARN: github.json missing — collaboration/influence will be empty",
              file=sys.stderr)
        gh = {"pull_requests": [], "reviews": {}, "issue_comments": {},
              "users": {}, "window_start": git["window_since"] + "T00:00:00+00:00",
              "repo": "PostHog/posthog"}

    result = compute(git, gh, DEFAULT_WEIGHTS)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)

    m = result["meta"]
    print(f"cohort_size={m['cohort_size']} ({m['cohort_threshold']})")
    print("Top 10 by composite:")
    for e in result["engineers"][:10]:
        p = e["pillars"]
        print(f"  #{e['rank']:>2} {e['composite']:>5.1f}  {e['name'][:24]:<24} "
              f"@{e['login']:<16} "
              f"A{p['authorship']:>3.0f} C{p['collaboration']:>3.0f} "
              f"O{p['ownership']:>3.0f} K{p['consistency']:>3.0f} I{p['influence']:>3.0f}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
