"""Maintainability risk signals — surfacing patterns that often indicate
debt accumulation, without claiming to measure code quality.

The tool does NOT read file content here. All three signals derive from:
- commit metadata + changed file paths (already collected by git_scan when
  ``--risk`` is set)
- PR metadata (state, merge time, etc.) already in PRScanResult
- the friction classifications already produced for the scan report

No external benchmarks, no "healthy / unhealthy" thresholds, no
prescriptions. Each signal is presented as fact; the reader judges.

The signals:

1. ``file_churn`` — files most-touched in the window. High churn often
   marks instability or AI re-writes that didn't land cleanly first time.
2. ``post_merge_fix_burst`` — for each merged PR, count commits within
   N days afterwards that touch any of the PR's changed files. A burst
   immediately after merge is a debt accumulation pattern.
3. ``revert_rate_trend`` — month-bucketed ratio of revert-tagged merged
   PRs over total merged PRs. Trend up = something getting worse.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import timedelta

from ai_eng_audit.models import Commit, PRClassification, PullRequest


@dataclass(frozen=True)
class FileChurn:
    path: str
    touch_count: int


@dataclass(frozen=True)
class PostMergeBurst:
    pr_number: int
    pr_title: str | None
    burst_commits: int  # commits within window touching any PR file
    burst_window_days: int


@dataclass(frozen=True)
class RevertRateMonth:
    year_month: str  # "YYYY-MM"
    merged: int
    reverted: int
    rate_pct: float  # 0..100


@dataclass(frozen=True)
class RiskSignals:
    file_churn: list[FileChurn]
    post_merge_bursts: list[PostMergeBurst]
    revert_rate_trend: list[RevertRateMonth]


def compute_risk(
    commits: list[Commit],
    prs: list[PullRequest],
    classifications: list[PRClassification],
    *,
    top_n_churn: int = 10,
    min_churn_touches: int = 3,
    burst_window_days: int = 7,
) -> RiskSignals:
    return RiskSignals(
        file_churn=_file_churn(commits, top_n=top_n_churn, min_touches=min_churn_touches),
        post_merge_bursts=_post_merge_bursts(
            commits, prs, burst_window_days=burst_window_days
        ),
        revert_rate_trend=_revert_rate_trend(classifications, prs),
    )


def _file_churn(
    commits: list[Commit], *, top_n: int, min_touches: int
) -> list[FileChurn]:
    counter: Counter = Counter()
    for c in commits:
        if c.files_touched:
            counter.update(c.files_touched)
    out = [
        FileChurn(path=path, touch_count=n)
        for path, n in counter.most_common(top_n)
        if n >= min_touches
    ]
    return out


def _post_merge_bursts(
    commits: list[Commit],
    prs: list[PullRequest],
    *,
    burst_window_days: int,
) -> list[PostMergeBurst]:
    commits_by_sha = {c.sha: c for c in commits}
    sorted_commits = sorted(commits, key=lambda c: c.authored_date)

    bursts: list[PostMergeBurst] = []
    for pr in prs:
        if pr.merged_at is None or pr.merge_commit_sha is None:
            continue
        merge_commit = commits_by_sha.get(pr.merge_commit_sha)
        if merge_commit is None or not merge_commit.files_touched:
            continue
        pr_files = set(merge_commit.files_touched)
        burst_end = pr.merged_at + timedelta(days=burst_window_days)

        count = 0
        for c in sorted_commits:
            if c.authored_date <= pr.merged_at:
                continue
            if c.authored_date > burst_end:
                break
            if c.files_touched and pr_files.intersection(c.files_touched):
                count += 1

        if count > 0:
            bursts.append(
                PostMergeBurst(
                    pr_number=pr.number,
                    pr_title=pr.title,
                    burst_commits=count,
                    burst_window_days=burst_window_days,
                )
            )
    # Sort by burst size descending
    bursts.sort(key=lambda b: b.burst_commits, reverse=True)
    return bursts


def _revert_rate_trend(
    classifications: list[PRClassification], prs: list[PullRequest]
) -> list[RevertRateMonth]:
    pr_by_number = {pr.number: pr for pr in prs}
    by_month: dict[tuple[int, int], dict[str, int]] = defaultdict(
        lambda: {"merged": 0, "reverted": 0}
    )
    for c in classifications:
        if c.ship_state != "l1_shipped":
            continue
        pr = pr_by_number.get(c.pr_number)
        if pr is None or pr.merged_at is None:
            continue
        key = (pr.merged_at.year, pr.merged_at.month)
        by_month[key]["merged"] += 1
        if "reverted_within_n" in c.friction_tags:
            by_month[key]["reverted"] += 1

    out: list[RevertRateMonth] = []
    for (yr, mo), data in sorted(by_month.items()):
        merged = data["merged"]
        reverted = data["reverted"]
        rate = (reverted / merged * 100) if merged else 0.0
        out.append(
            RevertRateMonth(
                year_month=f"{yr}-{mo:02d}",
                merged=merged,
                reverted=reverted,
                rate_pct=rate,
            )
        )
    return out
