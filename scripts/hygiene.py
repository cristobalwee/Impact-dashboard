"""
hygiene.py — shared data-hygiene layer for the impact rubric.

Owns three concerns that the rest of the pipeline depends on:
  1. Bot detection (drop automation accounts).
  2. Generated/vendored file exclusion (don't credit lockfiles, snapshots, migrations).
  3. Directory weighting (source 1.0 > tests 0.7 > docs/config 0.4).
  4. Identity canonicalization (merge duplicate humans by email/login).

Keep the globs here so there is exactly one place to tune what "real, human,
meaningful code" means for PostHog.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# 1. Bots
# --------------------------------------------------------------------------- #

# Explicit denylist of known automation accounts in/around PostHog.
BOT_LOGINS = {
    "dependabot[bot]",
    "dependabot-preview[bot]",
    "github-actions[bot]",
    "posthog-bot",
    "posthog-contributions-bot[bot]",
    "renovate[bot]",
    "renovate-bot",
    "snyk-bot",
    "imgbot[bot]",
    "pre-commit-ci[bot]",
    "sentry-io[bot]",
    "codecov[bot]",
    "greenkeeper[bot]",
    "web-flow",  # GitHub's merge-commit identity
}

BOT_EMAIL_SUBSTRINGS = (
    "[bot]",
    "bot@",
    "noreply@github.com",
    "actions@github.com",
)


def is_bot(login: str | None = None, name: str | None = None, email: str | None = None) -> bool:
    """True if any identity field looks like an automation account."""
    login = (login or "").strip().lower()
    name = (name or "").strip().lower()
    email = (email or "").strip().lower()

    if login in BOT_LOGINS or name in BOT_LOGINS:
        return True
    # Any login/name ending in 'bot' or '[bot]'.
    for ident in (login, name):
        if ident.endswith("[bot]") or ident.endswith("-bot") or ident.endswith(" bot"):
            return True
        if ident.endswith("bot") and len(ident) > 3 and not ident.endswith("abbot"):
            # crude but effective; deny 'foo-bot', 'foobot'. Whitelist real names if needed.
            if re.search(r"(^|[^a-z])bot$", ident) or ident.endswith("bot"):
                return True
    if any(sub in email for sub in BOT_EMAIL_SUBSTRINGS):
        return True
    return False


# --------------------------------------------------------------------------- #
# 2. Generated / vendored files (excluded from churn, ownership, survival)
# --------------------------------------------------------------------------- #

EXCLUDED_GLOBS = (
    # lockfiles
    "*.lock",
    "*/yarn.lock",
    "*/pnpm-lock.yaml",
    "*/package-lock.json",
    "*/poetry.lock",
    "*/Pipfile.lock",
    "*/Cargo.lock",
    # minified / built
    "*.min.js",
    "*.min.css",
    "*.map",
    "*/dist/*",
    "*/build/*",
    # vendored
    "*/vendor/*",
    "*/node_modules/*",
    "*/third_party/*",
    # snapshots / fixtures (PostHog uses syrupy *.ambr + jest __snapshots__)
    "*.ambr",
    "*.snap",
    "*/__snapshots__/*",
    "*/__snapshot__/*",
    "*/snapshots/*",
    # generated schemas / types (PostHog generates these from source-of-truth)
    "*/schema.json",
    "*/queries/schema/*",
    "*.generated.*",
    "*generated.ts",
    "*generated.js",
    "*generated.py",
    "*generated.go",
    "*/generated/*",
    "*/gen/*",
    # generated test-timing / snapshot manifests
    "*.test_durations",
    "*/.test_durations",
    "*/snapshots.yml",
    "*/snapshots.yaml",
    "*/__mocks__/*.json",
    # Django/ORM migrations are machine-generated
    "*/migrations/*.py",
    "*/migrations/*.sql",
    # mypy / lint baselines
    "*mypy-baseline*",
    # binaries / assets
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.svg",
    "*.woff",
    "*.woff2",
    "*.ttf",
    "*.eot",
    "*.pdf",
    "*.mp4",
    "*.mov",
    "*.parquet",
    # data dumps / fixtures
    "*.csv",
    "*/fixtures/*",
)


def is_excluded_file(path: str) -> bool:
    """True if the path is generated/vendored/binary and must not count."""
    p = path.strip()
    # Normalise so leading-segment globs ('*/x') also match top-level 'x'.
    candidates = (p, "/" + p)
    for pattern in EXCLUDED_GLOBS:
        if any(fnmatch.fnmatch(c, pattern) for c in candidates):
            return True
    return False


# --------------------------------------------------------------------------- #
# 3. Directory weighting
# --------------------------------------------------------------------------- #

_TEST_MARKERS = (
    "/tests/",
    "/test/",
    "/__tests__/",
    "/e2e/",
    "/cypress/",
    "/playwright/",
    ".test.",
    ".spec.",
    "_test.py",
    "test_",
)

_DOC_CONFIG_EXTS = (
    ".md",
    ".mdx",
    ".rst",
    ".txt",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".json",
    ".env",
    ".editorconfig",
)

_DOC_CONFIG_MARKERS = (
    "/docs/",
    "/.github/",
    "/config/",
    "requirements",
    "dockerfile",
    "docker-compose",
)


def dir_weight(path: str) -> float:
    """Source 1.0 > tests 0.7 > docs/config 0.4."""
    p = path.lower()
    if any(m in p for m in _TEST_MARKERS):
        return 0.7
    if p.endswith(_DOC_CONFIG_EXTS) or any(m in p for m in _DOC_CONFIG_MARKERS):
        return 0.4
    return 1.0


# --------------------------------------------------------------------------- #
# 4. Identity canonicalization
# --------------------------------------------------------------------------- #


@dataclass
class Identity:
    canonical_id: str
    name: str = ""
    login: str = ""
    avatar_url: str = ""
    emails: set[str] = field(default_factory=set)
    logins: set[str] = field(default_factory=set)


class IdentityResolver:
    """
    Union-find over (email, login) so the same human collapses to one node.

    Feed it observations from git (name/email) and GitHub (login/email/avatar).
    Merge rule: shared email OR shared login => same person. git already applies
    the repo .mailmap, so most email aliasing is handled upstream; this catches
    the rest and bridges git-email <-> github-login.
    """

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}
        self._info: dict[str, Identity] = {}

    @staticmethod
    def _email_key(email: str) -> str:
        return "email:" + email.strip().lower()

    @staticmethod
    def _login_key(login: str) -> str:
        return "login:" + login.strip().lower()

    def _find(self, k: str) -> str:
        self._parent.setdefault(k, k)
        root = k
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[k] != root:
            self._parent[k], k = root, self._parent[k]
        return root

    def _union(self, a: str, b: str) -> None:
        ra, rb = self._find(a), self._find(b)
        if ra != rb:
            self._parent[rb] = ra

    def observe(
        self,
        *,
        name: str = "",
        login: str = "",
        email: str = "",
        avatar_url: str = "",
    ) -> None:
        keys = []
        if email:
            keys.append(self._email_key(email))
        if login:
            keys.append(self._login_key(login))
        if not keys:
            return
        for k in keys:
            self._find(k)
        for k in keys[1:]:
            self._union(keys[0], k)
        # stash raw attrs against each key for later rollup
        root = self._find(keys[0])
        info = self._info.setdefault(root, Identity(canonical_id=root))
        if email:
            info.emails.add(email.strip().lower())
        if login:
            info.logins.add(login.strip().lower())
        if name and not info.name:
            info.name = name
        if login and not info.login:
            info.login = login
        if avatar_url and not info.avatar_url:
            info.avatar_url = avatar_url

    def _rollup(self) -> dict[str, Identity]:
        """Collapse stashed info onto current roots (parents may have changed)."""
        merged: dict[str, Identity] = {}
        for _, info in self._info.items():
            anchor = next(iter(info.emails | info.logins), None)
            if anchor is None:
                continue
            key = (
                self._email_key(next(iter(info.emails)))
                if info.emails
                else self._login_key(next(iter(info.logins)))
            )
            root = self._find(key)
            tgt = merged.setdefault(root, Identity(canonical_id=root))
            tgt.emails |= info.emails
            tgt.logins |= info.logins
            tgt.name = tgt.name or info.name
            tgt.login = tgt.login or info.login
            tgt.avatar_url = tgt.avatar_url or info.avatar_url
        return merged

    def canonical_for_email(self, email: str) -> str:
        return self._find(self._email_key(email))

    def canonical_for_login(self, login: str) -> str:
        return self._find(self._login_key(login))

    def identities(self) -> dict[str, Identity]:
        """Map of canonical_id -> Identity, with a stable human-readable id."""
        merged = self._rollup()
        out: dict[str, Identity] = {}
        for root, info in merged.items():
            # Prefer a login as the canonical id; fall back to first email.
            cid = info.login or (sorted(info.logins)[0] if info.logins else "")
            cid = cid or (sorted(info.emails)[0] if info.emails else root)
            info.canonical_id = cid
            out[cid] = info
        return out


if __name__ == "__main__":
    # Tiny self-test.
    assert is_bot(login="dependabot[bot]")
    assert is_bot(login="renovate[bot]")
    assert is_bot(email="49699333+dependabot[bot]@users.noreply.github.com")
    assert not is_bot(login="timgl", name="Tim Glaser", email="tim@posthog.com")
    assert is_excluded_file("pnpm-lock.yaml")
    assert is_excluded_file("frontend/src/queries/schema/schema-general.json")
    assert is_excluded_file("posthog/migrations/0001_initial.py")
    assert is_excluded_file("frontend/__snapshots__/foo.test.ts.snap")
    assert not is_excluded_file("posthog/api/capture.py")
    assert dir_weight("posthog/api/capture.py") == 1.0
    assert dir_weight("posthog/api/test/test_capture.py") == 0.7
    assert dir_weight("README.md") == 0.4
    print("hygiene self-test OK")
