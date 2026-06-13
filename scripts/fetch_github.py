"""
fetch_github.py — GitHub collaboration data via the GraphQL API (batched + cached).

Why GraphQL: one query returns a PR together with its reviews and comments, so a
busy repo like PostHog costs ~tens of requests instead of thousands of REST
round-trips, and dodges secondary rate limits.

Produces data/raw/github.json:
  - pull_requests : number, author login, createdAt/mergedAt/updatedAt, state
  - reviews       : per PR -> [{login, state, body_len, comment_count, submittedAt}]
  - issue_comments: per PR -> [{login, createdAt}]
  - users         : login -> {name, avatar_url}

We page PRs by UPDATED_AT desc and stop once a PR's updatedAt predates the
window (no further reviews can land in-window). Each raw page is cached to
data/raw/github_pages/ so re-runs are free. Token via GITHUB_TOKEN only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import hygiene

GQL_URL = "https://api.github.com/graphql"

QUERY = """
query($owner:String!, $name:String!, $cursor:String) {
  repository(owner:$owner, name:$name) {
    pullRequests(first:40, after:$cursor, orderBy:{field:UPDATED_AT, direction:DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        state
        createdAt
        mergedAt
        updatedAt
        author { login ... on User { name avatarUrl } }
        reviews(first:100) {
          totalCount
          nodes {
            state
            bodyText
            submittedAt
            author { login ... on User { name avatarUrl } }
            comments { totalCount }
          }
        }
        comments(first:100) {
          totalCount
          nodes {
            createdAt
            author { login ... on User { name avatarUrl } }
          }
        }
      }
    }
  }
  rateLimit { remaining cost resetAt }
}
"""


def gql(token: str, variables: dict, retries: int = 5) -> dict:
    body = json.dumps({"query": QUERY, "variables": variables}).encode()
    req = urllib.request.Request(
        GQL_URL, data=body, method="POST",
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "impact-dashboard",
        },
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read())
            if "errors" in payload:
                # Abuse/rate errors -> back off; schema errors -> raise.
                msg = json.dumps(payload["errors"])
                if "RATE_LIMITED" in msg or "abuse" in msg.lower():
                    wait = 2 ** attempt * 5
                    print(f"  rate/abuse, sleeping {wait}s: {msg[:120]}", flush=True)
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"GraphQL errors: {msg[:500]}")
            return payload["data"]
        except urllib.error.HTTPError as e:
            wait = 2 ** attempt * 5
            print(f"  HTTP {e.code}, sleeping {wait}s", flush=True)
            time.sleep(wait)
        except urllib.error.URLError as e:
            wait = 2 ** attempt * 3
            print(f"  net error {e}, sleeping {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError("exhausted retries against GraphQL API")


def _user(node: dict | None) -> tuple[str, str, str]:
    """Return (login, name, avatar) from an author node, tolerant of nulls."""
    if not node:
        return "", "", ""
    return (
        (node.get("login") or ""),
        (node.get("name") or ""),
        (node.get("avatarUrl") or ""),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="PostHog/posthog")
    ap.add_argument("--out", default="data/raw/github.json")
    ap.add_argument("--window-days", type=int, default=90)
    ap.add_argument("--cache-dir", default="data/raw/github_pages")
    ap.add_argument("--refresh", action="store_true", help="ignore cached pages")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("ERROR: GITHUB_TOKEN not set. `export GITHUB_TOKEN=...` and retry.",
              file=sys.stderr)
        return 2

    owner, name = args.repo.split("/")
    window_start = datetime.now(timezone.utc) - timedelta(days=args.window_days)
    os.makedirs(args.cache_dir, exist_ok=True)

    pull_requests: list[dict] = []
    reviews: dict[int, list] = {}
    issue_comments: dict[int, list] = {}
    users: dict[str, dict] = {}

    cursor = None
    page = 0
    stop = False
    while not stop:
        page += 1
        cache_path = os.path.join(args.cache_dir, f"page_{page:04d}.json")
        if os.path.exists(cache_path) and not args.refresh:
            with open(cache_path) as f:
                data = json.load(f)
            print(f"page {page}: cache hit", flush=True)
        else:
            data = gql(token, {"owner": owner, "name": name, "cursor": cursor})
            with open(cache_path, "w") as f:
                json.dump(data, f)
            rl = data.get("rateLimit", {})
            print(f"page {page}: fetched (cost={rl.get('cost')} "
                  f"remaining={rl.get('remaining')})", flush=True)

        conn = data["repository"]["pullRequests"]
        for pr in conn["nodes"]:
            updated = datetime.fromisoformat(pr["updatedAt"].replace("Z", "+00:00"))
            if updated < window_start:
                stop = True  # ordered desc -> everything after is older too
                break

            a_login, a_name, a_avatar = _user(pr.get("author"))
            if a_login and not hygiene.is_bot(login=a_login, name=a_name):
                users.setdefault(a_login, {"name": a_name, "avatar_url": a_avatar})

            pull_requests.append({
                "number": pr["number"],
                "state": pr["state"],
                "author": a_login,
                "createdAt": pr["createdAt"],
                "mergedAt": pr["mergedAt"],
                "updatedAt": pr["updatedAt"],
            })

            rv_list = []
            for rv in pr["reviews"]["nodes"]:
                r_login, r_name, r_avatar = _user(rv.get("author"))
                if not r_login or hygiene.is_bot(login=r_login, name=r_name):
                    continue
                users.setdefault(r_login, {"name": r_name, "avatar_url": r_avatar})
                rv_list.append({
                    "login": r_login,
                    "state": rv["state"],
                    "body_len": len((rv.get("bodyText") or "").strip()),
                    "comment_count": rv.get("comments", {}).get("totalCount", 0),
                    "submittedAt": rv.get("submittedAt"),
                    "pr_author": a_login,
                })
            reviews[pr["number"]] = rv_list

            ic_list = []
            for ic in pr["comments"]["nodes"]:
                c_login, c_name, c_avatar = _user(ic.get("author"))
                if not c_login or hygiene.is_bot(login=c_login, name=c_name):
                    continue
                users.setdefault(c_login, {"name": c_name, "avatar_url": c_avatar})
                ic_list.append({"login": c_login, "createdAt": ic["createdAt"]})
            issue_comments[pr["number"]] = ic_list

        if not stop:
            if conn["pageInfo"]["hasNextPage"]:
                cursor = conn["pageInfo"]["endCursor"]
            else:
                stop = True

    out = {
        "repo": args.repo,
        "window_days": args.window_days,
        "window_start": window_start.isoformat(),
        "pull_requests": pull_requests,
        "reviews": reviews,
        "issue_comments": issue_comments,
        "users": users,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f)
    print(f"wrote {args.out}: {len(pull_requests)} PRs, "
          f"{sum(len(v) for v in reviews.values())} reviews, "
          f"{len(users)} users", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
