"""Core data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from ai_eng_audit import METHODOLOGY_VERSION


ScopeAlignment = Literal["aligned", "partial", "mismatch"]


@dataclass(frozen=True)
class Commit:
    """A single commit from git history.

    files_touched stays None unless the scanner is explicitly asked to read it.
    """

    sha: str
    author_email: str
    author_name: str
    authored_date: datetime
    committed_date: datetime
    parent_shas: tuple[str, ...]
    subject: str | None = None
    files_touched: tuple[str, ...] | None = None


@dataclass(frozen=True)
class AuditWindow:
    """Time range a scan covers. spec is the raw user input string ("90d")."""

    start: datetime
    end: datetime
    spec: str


@dataclass
class GitScanResult:
    """Output of scanning one repo's git history."""

    repo_path: Path
    default_branch: str
    window: AuditWindow
    commits: list[Commit]


@dataclass(frozen=True)
class PullRequest:
    """A PR as seen via the host (GitHub / GitLab) API.

    Join with Commit one-way: PR.merge_commit_sha -> Commit.sha.
    """

    number: int
    title: str | None
    author_login: str
    state: str  # "OPEN" | "CLOSED" | "MERGED" as reported by the host
    is_draft: bool
    created_at: datetime
    closed_at: datetime | None
    merged_at: datetime | None
    merge_commit_sha: str | None
    head_ref: str | None
    base_ref: str
    changed_files: tuple[str, ...] | None = None


@dataclass
class PRScanResult:
    """Output of scanning one repo's PR history via the host API.

    truncated is True when the scan hit the per-call PR limit and may have
    missed PRs whose state still falls within the window. The renderer surfaces
    this so partial-data reports cannot be mistaken for complete ones.
    """

    repo_path: Path
    window: AuditWindow
    prs: list[PullRequest]
    truncated: bool = False


ShipState = Literal["l1_shipped", "in_flight", "not_l1_shipped", "ambiguous"]
Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class PRClassification:
    """Ship state + friction tags for one PR.

    headline_eligible = False means the classification is shown only in detail
    view, never aggregated into headline counts (per methodology §3.1, §3.2
    on candidate sub-classes). 1B emits high-confidence headline_eligible=True
    only; lower-confidence sub-classes arrive in later increments.
    """

    pr_number: int
    ship_state: ShipState
    friction_tags: tuple[str, ...]
    headline_eligible: bool
    confidence: Confidence


@dataclass(frozen=True)
class BillingPeriod:
    """One day of AI spend from one vendor, after normalization."""

    date: date
    cost_usd: Decimal
    vendor: str  # "anthropic" | "openrouter" | future vendor key


@dataclass
class BillingScanResult:
    """Output of parsing one or more billing CSVs.

    scope is the user-declared alignment between billing scope and the
    throughput scan (per methodology §"Spend ↔ Throughput"). Default
    `mismatch` because most billing exports are org-level while throughput
    is repo-level.

    skipped_rows is the total number of CSV rows that could not be parsed
    across all files (e.g., malformed date or amount); surfaced so a
    partially-broken CSV does not silently inflate or undercount spend.
    """

    periods: list[BillingPeriod]
    source_files: list[Path]
    vendors: tuple[str, ...]
    scope: ScopeAlignment
    skipped_rows: int = 0


@dataclass
class Report:
    """Top-level scan report. Tier 2 attribution will join later.

    errors maps scan-component name -> error message for scans that were
    requested but failed (e.g., {'pr': 'GITHUB_TOKEN invalid', 'billing':
    'CSV format unrecognized'}). Distinguishes "scan skipped" (key absent,
    field None) from "scan failed" (key present with reason). Text renderer
    surfaces these in the headline; JSON consumers see the dict directly.
    """

    git: GitScanResult
    pr: PRScanResult | None = None
    classifications: list[PRClassification] = field(default_factory=list)
    billing: BillingScanResult | None = None
    errors: dict[str, str] = field(default_factory=dict)
    methodology_version: str = METHODOLOGY_VERSION
