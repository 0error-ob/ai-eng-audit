"""Unit tests for the derived 'notable contrasts' annotations."""

from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from ai_eng_audit.annotations import compute_annotations
from ai_eng_audit.models import (
    AuditWindow,
    BillingPeriod,
    BillingScanResult,
    Commit,
    GitScanResult,
    PRClassification,
    PRScanResult,
    PullRequest,
    Report,
)


_NOW = datetime(2026, 5, 27, tzinfo=timezone.utc)
_WINDOW = AuditWindow(start=_NOW - timedelta(days=90), end=_NOW, spec="90d")


def _commit(email: str, days_ago: int) -> Commit:
    when = _NOW - timedelta(days=days_ago)
    return Commit(
        sha=f"sha-{email}-{days_ago}",
        author_email=email,
        author_name=email.split("@")[0],
        authored_date=when,
        committed_date=when,
        parent_shas=(),
        subject="commit",
    )


def _pr(
    number: int, *, state: str, created_days_ago: int, closed_days_ago: int | None = None
) -> PullRequest:
    created = _NOW - timedelta(days=created_days_ago)
    closed = _NOW - timedelta(days=closed_days_ago) if closed_days_ago else None
    return PullRequest(
        number=number,
        title=f"PR #{number}",
        author_login="alice",
        state=state,
        is_draft=False,
        created_at=created,
        closed_at=closed,
        merged_at=closed if state == "CLOSED" else None,
        merge_commit_sha=f"sha{number}" if state == "CLOSED" else None,
        head_ref=f"head-{number}",
        base_ref="main",
    )


def _report(*, commits=None, prs=None, classifications=None, billing=None) -> Report:
    return Report(
        git=GitScanResult(
            repo_path=Path("/tmp/synth"),
            default_branch="main",
            window=_WINDOW,
            commits=list(commits or []),
        ),
        pr=(
            PRScanResult(
                repo_path=Path("/tmp/synth"),
                window=_WINDOW,
                prs=list(prs or []),
            )
            if prs is not None
            else None
        ),
        classifications=list(classifications or []),
        billing=billing,
    )


class WipFlowAnnotationTests(unittest.TestCase):
    def test_wip_flow_positive_when_more_created_than_closed(self):
        prs = [
            _pr(1, state="OPEN", created_days_ago=10),
            _pr(2, state="OPEN", created_days_ago=8),
            _pr(3, state="CLOSED", created_days_ago=5, closed_days_ago=3),
        ]
        cls = [
            PRClassification(
                pr_number=p.number,
                ship_state="in_flight" if p.state == "OPEN" else "l1_shipped",
                friction_tags=(),
                headline_eligible=True,
                confidence="high",
            )
            for p in prs
        ]
        annotations = compute_annotations(
            _report(prs=prs, classifications=cls), _WINDOW, pr_available=True
        )

        wip = next(a for a in annotations if a.key == "a_wip_change")
        self.assertEqual(wip.values["opened"], 3)
        self.assertEqual(wip.values["resolved"], 1)
        self.assertEqual(wip.values["n"], 2)
        self.assertEqual(wip.values["sign"], "+")


class ContributorConcentrationTests(unittest.TestCase):
    def test_top_n_share_computed(self):
        commits = (
            [_commit("alice@example.com", d) for d in range(80)]
            + [_commit("bob@example.com", d) for d in range(10)]
            + [_commit("carol@example.com", d) for d in range(10)]
        )
        annotations = compute_annotations(
            _report(commits=commits), _WINDOW, pr_available=False
        )

        cc = next(a for a in annotations if a.key == "a_contributor_concentration")
        self.assertEqual(cc.values["total"], 3)
        # top-3 covers all authors so share is 100%
        self.assertAlmostEqual(cc.values["pct"], 100.0)

    def test_no_concentration_when_single_author(self):
        commits = [_commit("alice@example.com", d) for d in range(5)]
        annotations = compute_annotations(
            _report(commits=commits), _WINDOW, pr_available=False
        )

        self.assertFalse(
            any(a.key == "a_contributor_concentration" for a in annotations)
        )


class MergeVelocityTests(unittest.TestCase):
    def test_merge_velocity_when_any_merged(self):
        prs = [_pr(i, state="CLOSED", created_days_ago=10, closed_days_ago=5) for i in range(9)]
        cls = [
            PRClassification(
                pr_number=p.number,
                ship_state="l1_shipped",
                friction_tags=(),
                headline_eligible=True,
                confidence="high",
            )
            for p in prs
        ]
        annotations = compute_annotations(
            _report(prs=prs, classifications=cls), _WINDOW, pr_available=True
        )

        mv = next(a for a in annotations if a.key == "a_merge_velocity")
        self.assertEqual(mv.values["merged"], 9)
        self.assertEqual(mv.values["days"], 90)
        self.assertAlmostEqual(mv.values["per_day"], 0.1)


class SpendPairingTests(unittest.TestCase):
    def _setup_with_billing(self, scope: str) -> Report:
        prs = [_pr(i, state="CLOSED", created_days_ago=20, closed_days_ago=10) for i in range(4)]
        cls = [
            PRClassification(
                pr_number=p.number,
                ship_state="l1_shipped",
                friction_tags=(),
                headline_eligible=True,
                confidence="high",
            )
            for p in prs
        ]
        billing = BillingScanResult(
            periods=[
                BillingPeriod(date=date(2026, 5, 15), cost_usd=Decimal("400.00"), vendor="anthropic"),
            ],
            source_files=[Path("/tmp/b.csv")],
            vendors=("anthropic",),
            scope=scope,
        )
        return _report(prs=prs, classifications=cls, billing=billing)

    def test_aligned_scope_emits_per_pr_cost(self):
        report = self._setup_with_billing("aligned")
        annotations = compute_annotations(report, _WINDOW, pr_available=True)

        a = next(a for a in annotations if a.key == "a_spend_per_pr_aligned")
        self.assertEqual(a.values["merged"], 4)
        self.assertEqual(a.values["total"], Decimal("400.00"))
        self.assertEqual(a.values["per_pr"], Decimal("100.00"))

    def test_mismatch_scope_does_not_compute_ratio(self):
        report = self._setup_with_billing("mismatch")
        annotations = compute_annotations(report, _WINDOW, pr_available=True)

        a = next(a for a in annotations if a.key == "a_spend_pairing_unaligned")
        self.assertEqual(a.values["scope"], "mismatch")
        self.assertNotIn("per_pr", a.values)


if __name__ == "__main__":
    unittest.main()
