"""Classify PRs by ship state and attach friction tags.

For 1B: ``abandoned``, ``long_lived_open``, ``reverted_within_n``. Other
tags from docs/methodology.md (``abandoned-with-replacement``,
``reverted-then-fixed``, closed-without-merge issues, review latency) need
data sources not in 1B and arrive later.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from ai_eng_audit.models import Commit, PRClassification, PullRequest, ShipState


_REVERT_SUBJECT_RE = re.compile(r'^Revert\s+"(?P<title>.+)"\s*$')


def classify_prs(
    prs: list[PullRequest],
    commits: list[Commit],
    *,
    now: datetime,
    revert_window_days: int = 14,
    long_lived_threshold_days: int = 30,
) -> list[PRClassification]:
    """Produce a classification for every PR.

    Reverted-within-N joins PR <-> commit via commit subject:
    a commit whose subject matches ``Revert "<title>"`` is checked against
    merged PRs with that title; if the revert commit's authored_date is
    within ``revert_window_days`` of the PR's merged_at, the PR gets the
    ``reverted_within_n`` tag.
    """
    merged_by_title: dict[str, list[PullRequest]] = {}
    for pr in prs:
        if pr.merged_at is not None and pr.title:
            merged_by_title.setdefault(pr.title, []).append(pr)

    reverted: set[int] = set()
    for c in commits:
        if not c.subject:
            continue
        m = _REVERT_SUBJECT_RE.match(c.subject)
        if not m:
            continue
        title = m.group("title")
        for candidate in merged_by_title.get(title, []):
            if candidate.merged_at is None:
                continue
            delta = c.authored_date - candidate.merged_at
            if timedelta(0) <= delta <= timedelta(days=revert_window_days):
                reverted.add(candidate.number)

    classifications: list[PRClassification] = []
    for pr in prs:
        tags: list[str] = []

        if pr.state == "CLOSED" and pr.merged_at is None:
            tags.append("abandoned")

        if (
            pr.state == "OPEN"
            and not pr.is_draft
            and (now - pr.created_at).days > long_lived_threshold_days
        ):
            tags.append("long_lived_open")

        if pr.number in reverted:
            tags.append("reverted_within_n")

        classifications.append(
            PRClassification(
                pr_number=pr.number,
                ship_state=_ship_state(pr),
                friction_tags=tuple(tags),
                headline_eligible=True,
                confidence="high",
            )
        )
    return classifications


def _ship_state(pr: PullRequest) -> ShipState:
    if pr.merged_at is not None:
        return "l1_shipped"
    if pr.state == "OPEN":
        return "in_flight"
    if pr.state == "CLOSED":
        return "not_l1_shipped"
    return "ambiguous"
