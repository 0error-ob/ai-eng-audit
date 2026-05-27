"""Read PR history from GitHub via the REST API.

Uses stdlib urllib only; no external dependencies. Authentication is via the
GITHUB_TOKEN environment variable or an explicit token argument. Origin remote
is read from the local git config to derive owner/repo.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Iterator

from ai_eng_audit.models import AuditWindow, PRScanResult, PullRequest


_GITHUB_API = "https://api.github.com"
_REMOTE_RE = re.compile(
    r"""
    ^(?:https?://(?:[^@/]+@)?github\.com/|git@github\.com:)
    (?P<owner>[^/]+)
    /
    (?P<repo>[^/]+?)
    (?:\.git)?
    /?$
    """,
    re.VERBOSE,
)


class PRScanError(RuntimeError):
    """Raised when the PR scan cannot complete (auth, remote, network, etc.)."""


def _parse_origin(remote_url: str) -> tuple[str, str]:
    m = _REMOTE_RE.match(remote_url.strip())
    if not m:
        raise PRScanError(
            f"origin remote does not look like a GitHub repo: {remote_url!r}"
        )
    return m["owner"], m["repo"]


def _detect_origin(repo: Path) -> tuple[str, str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise PRScanError(f"no 'origin' remote in {repo}") from e
    return _parse_origin(result.stdout)


def _parse_iso(s: str | None) -> datetime | None:
    if s is None:
        return None
    # GitHub uses 'Z'; fromisoformat accepts '+00:00' but not 'Z' before 3.11.
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _iter_pages(url: str, token: str) -> Iterator[list[dict]]:
    while url:
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "ai-eng-audit",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                link = resp.headers.get("Link", "") or ""
            yield json.loads(body)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise PRScanError("GITHUB_TOKEN is missing or invalid") from e
            if e.code == 403:
                raise PRScanError(
                    f"GitHub API forbidden (rate limit or scope?): {e.reason}"
                ) from e
            if e.code == 404:
                raise PRScanError(f"GitHub repo not found or no access: {url}") from e
            raise PRScanError(f"GitHub API error {e.code}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise PRScanError(f"GitHub API network error: {e.reason}") from e
        except TimeoutError as e:
            raise PRScanError("GitHub API timed out") from e
        except json.JSONDecodeError as e:
            raise PRScanError(f"GitHub API returned invalid JSON: {e}") from e
        next_url = None
        for part in link.split(","):
            m = re.match(r'\s*<([^>]+)>;\s*rel="next"', part)
            if m:
                next_url = m.group(1)
                break
        url = next_url or ""


def _touches_window(
    window: AuditWindow, created: datetime, closed: datetime | None
) -> bool:
    """A PR was open at any moment inside the window."""
    return created < window.end and (closed is None or closed >= window.start)


def scan_prs(
    repo: Path,
    window: AuditWindow,
    *,
    limit: int = 1000,
    token: str | None = None,
) -> PRScanResult:
    """Scan PRs that overlap the audit window via the GitHub REST API.

    Returns at most `limit` PRs. Pages are sorted by `updated_at` desc, so we
    stop early once we see PRs whose last activity is older than window.start.
    """
    token = token or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise PRScanError(
            "GITHUB_TOKEN env var not set. Generate a PAT at "
            "https://github.com/settings/tokens with 'repo' scope."
        )
    owner, repo_name = _detect_origin(repo)
    prs: list[PullRequest] = []

    # Two passes. Closed first so we always sample merged PRs (ship rate stays
    # meaningful even when the limit clips the open pass). Open second without
    # early-stop because a stale long-open PR can have updated_at well before
    # window.start. Closed can early-stop safely: a closed PR's state cannot
    # drift back into the window without a new update event.
    for state, allow_early_stop in (("closed", True), ("open", False)):
        url = (
            f"{_GITHUB_API}/repos/{owner}/{repo_name}/pulls"
            f"?state={state}&per_page=100&sort=updated&direction=desc"
        )
        if _collect(url, token, window, limit, prs, allow_early_stop=allow_early_stop):
            return PRScanResult(
                repo_path=repo.resolve(), window=window, prs=prs, truncated=True
            )
    return PRScanResult(repo_path=repo.resolve(), window=window, prs=prs)


def _collect(
    url: str,
    token: str,
    window: AuditWindow,
    limit: int,
    prs: list[PullRequest],
    *,
    allow_early_stop: bool,
) -> bool:
    """Append matching PRs to `prs`. Returns True if `limit` was hit (truncated)."""
    for page in _iter_pages(url, token):
        for raw in page:
            if allow_early_stop:
                updated = _parse_iso(raw.get("updated_at"))
                if updated is not None and updated < window.start:
                    return False

            created = _parse_iso(raw["created_at"])
            closed = _parse_iso(raw.get("closed_at"))
            merged = _parse_iso(raw.get("merged_at"))

            if created is None or not _touches_window(window, created, closed):
                continue

            prs.append(
                PullRequest(
                    number=raw["number"],
                    title=raw.get("title"),
                    author_login=(raw.get("user") or {}).get("login", ""),
                    state=str(raw.get("state", "")).upper(),
                    is_draft=bool(raw.get("draft", False)),
                    created_at=created,
                    closed_at=closed,
                    merged_at=merged,
                    merge_commit_sha=raw.get("merge_commit_sha"),
                    head_ref=(raw.get("head") or {}).get("ref"),
                    base_ref=(raw.get("base") or {}).get("ref", "main"),
                )
            )
            if len(prs) >= limit:
                return True
    return False
