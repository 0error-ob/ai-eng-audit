"""Unit tests for maintainability risk signals."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from ai_eng_audit.models import Commit, PRClassification, PullRequest
from ai_eng_audit.risk import (
    FileChurn,
    PostMergeBurst,
    RevertRateMonth,
    compute_risk,
)


_NOW = datetime(2026, 5, 27, tzinfo=timezone.utc)


def _commit(
    sha: str,
    *,
    days_ago: int = 0,
    files: tuple[str, ...] | None = None,
    subject: str = "feat",
) -> Commit:
    when = _NOW - timedelta(days=days_ago)
    return Commit(
        sha=sha,
        author_email="alice@example.com",
        author_name="alice",
        authored_date=when,
        committed_date=when,
        parent_shas=(),
        subject=subject,
        files_touched=files,
    )


def _pr(
    number: int,
    *,
    state: str = "CLOSED",
    days_ago_merged: int | None = None,
    merge_sha: str | None = None,
) -> PullRequest:
    merged = (
        _NOW - timedelta(days=days_ago_merged) if days_ago_merged is not None else None
    )
    return PullRequest(
        number=number,
        title=f"PR #{number}",
        author_login="alice",
        state=state,
        is_draft=False,
        created_at=merged - timedelta(days=2) if merged else _NOW,
        closed_at=merged,
        merged_at=merged,
        merge_commit_sha=merge_sha,
        head_ref=f"head-{number}",
        base_ref="main",
    )


def _classification(pr_number: int, *, shipped: bool, reverted: bool) -> PRClassification:
    return PRClassification(
        pr_number=pr_number,
        ship_state="l1_shipped" if shipped else "in_flight",
        friction_tags=("reverted_within_n",) if reverted else (),
        headline_eligible=True,
        confidence="high",
    )


class FileChurnTests(unittest.TestCase):
    def test_top_files_by_touch_count(self):
        commits = [
            _commit("a", files=("src/foo.py",)),
            _commit("b", files=("src/foo.py", "src/bar.py")),
            _commit("c", files=("src/foo.py", "src/bar.py", "src/baz.py")),
        ]
        risk = compute_risk(commits, [], [], min_churn_touches=2)
        churn = risk.file_churn
        # foo.py touched 3 times, bar.py 2, baz.py 1 (filtered out by min=2)
        paths = [fc.path for fc in churn]
        self.assertEqual(paths, ["src/foo.py", "src/bar.py"])
        self.assertEqual(churn[0].touch_count, 3)
        self.assertEqual(churn[1].touch_count, 2)

    def test_min_touches_filters_low_count(self):
        commits = [_commit("a", files=("rare.py",))]
        risk = compute_risk(commits, [], [], min_churn_touches=3)
        self.assertEqual(risk.file_churn, [])

    def test_no_files_touched_yields_empty(self):
        commits = [_commit("a", files=None)]
        risk = compute_risk(commits, [], [])
        self.assertEqual(risk.file_churn, [])


class PostMergeBurstTests(unittest.TestCase):
    def test_burst_detected_when_same_files_touched_within_window(self):
        # PR merged 10 days ago, merge commit touched foo.py
        # Two follow-up commits within 7d also touched foo.py
        commits = [
            _commit("merge1", days_ago=10, files=("foo.py",)),
            _commit("fix1", days_ago=8, files=("foo.py",)),
            _commit("fix2", days_ago=5, files=("foo.py", "bar.py")),
            _commit("unrelated", days_ago=3, files=("baz.py",)),
        ]
        prs = [_pr(1, days_ago_merged=10, merge_sha="merge1")]
        risk = compute_risk(commits, prs, [])
        self.assertEqual(len(risk.post_merge_bursts), 1)
        b = risk.post_merge_bursts[0]
        self.assertEqual(b.pr_number, 1)
        self.assertEqual(b.burst_commits, 2)

    def test_burst_excludes_commits_outside_window(self):
        # Follow-up 10d after merge (outside default 7d window)
        commits = [
            _commit("merge1", days_ago=20, files=("foo.py",)),
            _commit("late", days_ago=8, files=("foo.py",)),  # 12d after merge
        ]
        prs = [_pr(1, days_ago_merged=20, merge_sha="merge1")]
        risk = compute_risk(commits, prs, [], burst_window_days=7)
        self.assertEqual(risk.post_merge_bursts, [])

    def test_burst_skipped_when_pr_not_merged(self):
        commits = [_commit("c1", days_ago=5, files=("foo.py",))]
        prs = [_pr(1, state="OPEN", days_ago_merged=None)]
        risk = compute_risk(commits, prs, [])
        self.assertEqual(risk.post_merge_bursts, [])


class RevertRateTrendTests(unittest.TestCase):
    def test_rate_per_month(self):
        # NOW = 2026-05-27. Pick day offsets that land cleanly per month.
        prs = [
            _pr(1, days_ago_merged=73, merge_sha="m1"),  # 2026-03-15
            _pr(2, days_ago_merged=63, merge_sha="m2"),  # 2026-03-25
            _pr(3, days_ago_merged=37, merge_sha="m3"),  # 2026-04-20
        ]
        classifications = [
            _classification(1, shipped=True, reverted=True),
            _classification(2, shipped=True, reverted=False),
            _classification(3, shipped=True, reverted=False),
        ]
        risk = compute_risk([], prs, classifications)
        # 2 months: March and April
        self.assertEqual(len(risk.revert_rate_trend), 2)
        # March: 1 reverted / 2 merged = 50%
        march = risk.revert_rate_trend[0]
        self.assertEqual(march.merged, 2)
        self.assertEqual(march.reverted, 1)
        self.assertAlmostEqual(march.rate_pct, 50.0)
        # April: 0 / 1 = 0%
        april = risk.revert_rate_trend[1]
        self.assertEqual(april.rate_pct, 0.0)

    def test_in_flight_prs_excluded_from_denominator(self):
        prs = [_pr(1, state="OPEN", days_ago_merged=None)]
        classifications = [_classification(1, shipped=False, reverted=False)]
        risk = compute_risk([], prs, classifications)
        self.assertEqual(risk.revert_rate_trend, [])


if __name__ == "__main__":
    unittest.main()
