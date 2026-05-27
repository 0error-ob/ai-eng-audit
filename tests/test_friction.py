"""Unit tests for the friction classifier (stdlib unittest, zero deps)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from ai_eng_audit.classify.friction import classify_prs
from ai_eng_audit.models import Commit, PullRequest


_NOW = datetime(2026, 5, 27, tzinfo=timezone.utc)


def _pr(
    number: int,
    *,
    title: str = "feat: thing",
    state: str = "OPEN",
    is_draft: bool = False,
    created_days_ago: int = 1,
    closed_days_ago: int | None = None,
    merged_days_ago: int | None = None,
    author: str = "alice",
) -> PullRequest:
    created = _NOW - timedelta(days=created_days_ago)
    closed = _NOW - timedelta(days=closed_days_ago) if closed_days_ago else None
    merged = _NOW - timedelta(days=merged_days_ago) if merged_days_ago else None
    return PullRequest(
        number=number,
        title=title,
        author_login=author,
        state=state,
        is_draft=is_draft,
        created_at=created,
        closed_at=closed,
        merged_at=merged,
        merge_commit_sha=f"sha{number}" if merged else None,
        head_ref=f"head-{number}",
        base_ref="main",
    )


def _commit(sha: str, subject: str, *, days_ago: int = 0) -> Commit:
    when = _NOW - timedelta(days=days_ago)
    return Commit(
        sha=sha,
        author_email="alice@example.com",
        author_name="alice",
        authored_date=when,
        committed_date=when,
        parent_shas=(),
        subject=subject,
    )


class FrictionClassifierTests(unittest.TestCase):
    def test_merged_pr_is_shipped_no_friction(self):
        prs = [_pr(1, state="CLOSED", merged_days_ago=3, closed_days_ago=3)]
        classifications = classify_prs(prs, [], now=_NOW)

        self.assertEqual(classifications[0].ship_state, "l1_shipped")
        self.assertEqual(classifications[0].friction_tags, ())

    def test_closed_without_merge_is_abandoned(self):
        prs = [_pr(1, state="CLOSED", closed_days_ago=5)]
        classifications = classify_prs(prs, [], now=_NOW)

        self.assertEqual(classifications[0].ship_state, "not_l1_shipped")
        self.assertIn("abandoned", classifications[0].friction_tags)

    def test_open_pr_in_flight_no_friction_when_fresh(self):
        prs = [_pr(1, state="OPEN", created_days_ago=5)]
        classifications = classify_prs(prs, [], now=_NOW)

        self.assertEqual(classifications[0].ship_state, "in_flight")
        self.assertEqual(classifications[0].friction_tags, ())

    def test_long_lived_open_flagged_after_threshold(self):
        prs = [_pr(1, state="OPEN", created_days_ago=45)]
        classifications = classify_prs(
            prs, [], now=_NOW, long_lived_threshold_days=30
        )

        self.assertIn("long_lived_open", classifications[0].friction_tags)

    def test_long_lived_open_not_flagged_when_draft(self):
        prs = [_pr(1, state="OPEN", is_draft=True, created_days_ago=45)]
        classifications = classify_prs(
            prs, [], now=_NOW, long_lived_threshold_days=30
        )

        self.assertNotIn("long_lived_open", classifications[0].friction_tags)

    def test_explicit_revert_within_n_flagged(self):
        prs = [_pr(1, title="fix: foo", state="CLOSED", merged_days_ago=10, closed_days_ago=10)]
        commits = [_commit("rev1", 'Revert "fix: foo"', days_ago=3)]
        classifications = classify_prs(
            prs, commits, now=_NOW, revert_window_days=14
        )

        self.assertIn("reverted_within_n", classifications[0].friction_tags)

    def test_explicit_revert_outside_n_not_flagged(self):
        prs = [_pr(1, title="fix: foo", state="CLOSED", merged_days_ago=30, closed_days_ago=30)]
        commits = [_commit("rev1", 'Revert "fix: foo"', days_ago=3)]
        classifications = classify_prs(
            prs, commits, now=_NOW, revert_window_days=14
        )

        self.assertNotIn("reverted_within_n", classifications[0].friction_tags)

    def test_non_revert_commit_does_not_flag(self):
        prs = [_pr(1, title="fix: foo", state="CLOSED", merged_days_ago=5, closed_days_ago=5)]
        commits = [_commit("c1", "feat: something else", days_ago=2)]
        classifications = classify_prs(
            prs, commits, now=_NOW, revert_window_days=14
        )

        self.assertNotIn("reverted_within_n", classifications[0].friction_tags)


if __name__ == "__main__":
    unittest.main()
