"""Derive "notable contrasts" from a Report — opt-in via ``--annotate``.

Every annotation is computed strictly from fields already shown elsewhere in
the report. No external benchmarks, no "healthy / unhealthy" labels, no
prescriptive suggestions. The point is to surface contrasts the reader might
miss while scanning raw numbers; the reader still does the judging.

See docs/methodology.md § "Notable contrasts" for definitions.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from ai_eng_audit.models import AuditWindow, Report


@dataclass(frozen=True)
class Annotation:
    """One derived observation. ``key`` indexes into the localized string table."""

    key: str
    values: Mapping[str, Any]


def compute_annotations(
    report: Report, window: AuditWindow, *, pr_available: bool
) -> list[Annotation]:
    annotations: list[Annotation] = []

    # ---------- WIP net change (PR-side; needs PR data) ----------
    if pr_available and report.pr is not None:
        prs = report.pr.prs
        window_start = window.start
        window_end = window.end
        created_in_window = sum(
            1 for pr in prs if window_start <= pr.created_at < window_end
        )
        resolved_in_window = sum(
            1
            for pr in prs
            if pr.closed_at is not None
            and window_start <= pr.closed_at < window_end
        )
        wip_delta = created_in_window - resolved_in_window
        annotations.append(
            Annotation(
                key="a_wip_change",
                values={
                    "sign": "+" if wip_delta >= 0 else "−",
                    "n": abs(wip_delta),
                    "opened": created_in_window,
                    "resolved": resolved_in_window,
                    "window": window.spec,
                },
            )
        )

    # ---------- Contributor concentration (git-side) ----------
    if report.git.commits:
        authors = Counter(c.author_email for c in report.git.commits)
        n_total = len(authors)
        if n_total > 1:
            top_n = min(5, n_total)
            top_share_pct = (
                sum(c for _, c in authors.most_common(top_n))
                / len(report.git.commits)
                * 100
            )
            author_pct = top_n / n_total * 100
            annotations.append(
                Annotation(
                    key="a_contributor_concentration",
                    values={
                        "top_n": top_n,
                        "total": n_total,
                        "pct": top_share_pct,
                        "author_pct": author_pct,
                    },
                )
            )

    # ---------- Merge throughput per day (PR-side) ----------
    if pr_available and report.pr is not None:
        n_merged = sum(
            1 for c in report.classifications if c.ship_state == "l1_shipped"
        )
        days = max((window.end - window.start).days, 1)
        if n_merged > 0:
            annotations.append(
                Annotation(
                    key="a_merge_velocity",
                    values={
                        "merged": n_merged,
                        "days": days,
                        "per_day": n_merged / days,
                    },
                )
            )

    # ---------- Spend pairing (when billing loaded) ----------
    if report.billing is not None:
        start_d = window.start.date()
        end_d = window.end.date()
        billing_total = sum(
            (p.cost_usd for p in report.billing.periods if start_d <= p.date < end_d),
            Decimal("0"),
        )
        n_merged = sum(
            1 for c in report.classifications if c.ship_state == "l1_shipped"
        ) if pr_available else 0

        if pr_available and n_merged > 0 and billing_total > 0:
            if report.billing.scope == "aligned":
                annotations.append(
                    Annotation(
                        key="a_spend_per_pr_aligned",
                        values={
                            "total": billing_total,
                            "merged": n_merged,
                            "per_pr": billing_total / n_merged,
                        },
                    )
                )
            else:
                # mismatch / partial: show both sides, decline the ratio.
                annotations.append(
                    Annotation(
                        key="a_spend_pairing_unaligned",
                        values={
                            "total": billing_total,
                            "merged": n_merged,
                            "scope": report.billing.scope,
                        },
                    )
                )

    return annotations
