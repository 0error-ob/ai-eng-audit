"""Parse AI vendor billing CSVs into a normalized daily-spend stream.

Supported vendors:
- ``anthropic`` — Anthropic Console cost export (the CSV that has ``cost_usd``).
  The tokens-only export from the same console is rejected with a clear message.
- ``openrouter`` — OpenRouter activity export.

Detection is by CSV header signature, so the user only passes ``--billing
<file>``; the parser picks the right code path.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ai_eng_audit.models import BillingPeriod, BillingScanResult, ScopeAlignment


class BillingScanError(RuntimeError):
    """Raised when a billing CSV cannot be parsed (unknown format, no costs, etc.)."""


def detect_vendor(path: Path) -> str:
    """Classify a CSV by its header row. Returns a vendor key, or raises."""
    with open(path, encoding="utf-8") as f:
        header = f.readline().strip().lower()
    if "usage_date_utc" in header and "cost_usd" in header:
        return "anthropic"
    if "usage_date_utc" in header and "usage_input_tokens" in header:
        raise BillingScanError(
            f"{path.name}: Anthropic tokens-only export (no cost column). "
            f"Use the cost CSV from the console instead."
        )
    if "date" in header and "slug" in header and "usage" in header:
        return "openrouter"
    raise BillingScanError(
        f"{path.name}: unrecognized billing CSV header: {header[:120]}"
    )


def parse_anthropic_cost(path: Path) -> tuple[list[BillingPeriod], int]:
    """Sum ``cost_usd`` per (date, vendor='anthropic').

    Returns ``(periods, skipped_row_count)``. A row is skipped when its date
    or cost cannot be parsed (most commonly because the CSV header drifted).
    """
    daily: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
    skipped = 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                d = date.fromisoformat(row["usage_date_utc"])
                daily[d] += Decimal(row["cost_usd"])
            except (KeyError, ValueError, InvalidOperation):
                skipped += 1
                continue
    periods = [
        BillingPeriod(date=d, cost_usd=c, vendor="anthropic")
        for d, c in sorted(daily.items())
    ]
    return periods, skipped


def parse_openrouter(path: Path) -> tuple[list[BillingPeriod], int]:
    """Sum ``Usage`` per (date, vendor='openrouter'). BYOK column is ignored
    because BYOK requests are not billed by OpenRouter.

    Returns ``(periods, skipped_row_count)`` — same contract as the
    Anthropic parser.
    """
    daily: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
    skipped = 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                date_str = row["Date"].split()[0]  # "YYYY-MM-DD HH:MM:SS" -> "YYYY-MM-DD"
                d = date.fromisoformat(date_str)
                daily[d] += Decimal(row["Usage"])
            except (KeyError, ValueError, InvalidOperation):
                skipped += 1
                continue
    periods = [
        BillingPeriod(date=d, cost_usd=c, vendor="openrouter")
        for d, c in sorted(daily.items())
    ]
    return periods, skipped


_PARSERS = {
    "anthropic": parse_anthropic_cost,
    "openrouter": parse_openrouter,
}


def scan_billing(
    paths: list[Path], scope: ScopeAlignment = "mismatch"
) -> BillingScanResult:
    """Parse one or more billing CSVs and merge into a single result.

    Each file is detected and parsed independently; days from different
    vendors stay distinct (one ``BillingPeriod`` per (date, vendor)) so a
    later renderer can choose to sum or break down by vendor.

    Caller is responsible for not passing overlapping CSVs (e.g., OpenRouter
    proxying calls also visible in the Anthropic Console). The methodology
    document spells this out.

    Raises ``BillingScanError`` if a file yields zero parseable rows while
    having had rows to parse — this typically means the vendor changed the
    CSV header and silent zero-cost output would be misleading.
    """
    periods: list[BillingPeriod] = []
    vendors: set[str] = set()
    total_skipped = 0
    for path in paths:
        vendor = detect_vendor(path)
        file_periods, file_skipped = _PARSERS[vendor](path)
        if not file_periods and file_skipped > 0:
            raise BillingScanError(
                f"{path.name}: no parseable cost rows (skipped {file_skipped}). "
                f"The {vendor} CSV header may have changed; verify the export "
                f"format hasn't drifted."
            )
        periods.extend(file_periods)
        vendors.add(vendor)
        total_skipped += file_skipped
    return BillingScanResult(
        periods=periods,
        source_files=paths,
        vendors=tuple(sorted(vendors)),
        scope=scope,
        skipped_rows=total_skipped,
    )
