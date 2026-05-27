"""Read git history for the audit window."""

from __future__ import annotations

import subprocess
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from ai_eng_audit.models import AuditWindow, Commit, GitScanResult


_PRETTY_FORMAT = "%H%x1f%ae%x1f%an%x1f%aI%x1f%cI%x1f%P%x1f%s"
_RECORD_SEP = "\x1e"
_FIELD_SEP = "\x1f"


def _run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def detect_default_branch(repo: Path) -> str:
    """Prefer origin's HEAD symref; fall back to main/master if no remote."""
    try:
        out = _run_git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
        return out.strip().removeprefix("origin/")
    except subprocess.CalledProcessError:
        pass
    for candidate in ("main", "master"):
        try:
            _run_git(repo, "rev-parse", "--verify", candidate)
            return candidate
        except subprocess.CalledProcessError:
            continue
    raise RuntimeError(f"could not determine default branch for {repo}")


def scan_commits(
    repo: Path, window: AuditWindow, *, include_files: bool = False
) -> GitScanResult:
    """Scan the default branch's commit log within the window.

    When ``include_files=True`` runs a second pass with ``--name-only
    --diff-merges=first-parent`` to populate ``Commit.files_touched``.
    Only file paths are read; file content is never opened. This is what
    the ``--risk`` flag in the CLI uses for churn / post-merge-burst
    signal computation.
    """
    default_branch = detect_default_branch(repo)
    out = _run_git(
        repo,
        "log",
        f"--pretty=format:{_PRETTY_FORMAT}{_RECORD_SEP}",
        f"--since={window.start.isoformat()}",
        f"--until={window.end.isoformat()}",
        default_branch,
    )
    commits: list[Commit] = []
    for raw in out.split(_RECORD_SEP):
        # Strip only newlines: str.strip() with default args eats \x1f / \x1e
        # (Python treats them as whitespace), which would corrupt our records.
        record = raw.strip("\n\r")
        if not record:
            continue
        parts = record.split(_FIELD_SEP)
        if len(parts) < 7:
            continue
        sha, email, name, authored, committed, parents, subject = parts[:7]
        commits.append(
            Commit(
                sha=sha,
                author_email=email,
                author_name=name,
                authored_date=datetime.fromisoformat(authored),
                committed_date=datetime.fromisoformat(committed),
                parent_shas=tuple(p for p in parents.split() if p),
                subject=subject,
            )
        )

    if include_files and commits:
        files_by_sha = _scan_files_per_commit(repo, window, default_branch)
        commits = [
            replace(c, files_touched=files_by_sha.get(c.sha)) for c in commits
        ]

    return GitScanResult(
        repo_path=repo.resolve(),
        default_branch=default_branch,
        window=window,
        commits=commits,
    )


def _scan_files_per_commit(
    repo: Path, window: AuditWindow, default_branch: str
) -> dict[str, tuple[str, ...]]:
    """Second pass: ``git log --name-only`` -> {sha: (files...)}."""
    out = _run_git(
        repo,
        "log",
        "--pretty=format:%H",
        "--name-only",
        "--diff-merges=first-parent",
        f"--since={window.start.isoformat()}",
        f"--until={window.end.isoformat()}",
        default_branch,
    )
    files_by_sha: dict[str, tuple[str, ...]] = {}
    # Each commit block is: sha\n file1\n file2\n ... separated by blank line.
    for block in out.split("\n\n"):
        lines = [line for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        sha = lines[0].strip()
        files = tuple(line.strip() for line in lines[1:] if line.strip())
        files_by_sha[sha] = files
    return files_by_sha
