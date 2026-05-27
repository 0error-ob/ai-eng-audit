"""CLI entry point."""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping, TextIO

from ai_eng_audit.annotations import compute_annotations
from ai_eng_audit.classify.friction import classify_prs
from ai_eng_audit.models import AuditWindow, BillingScanResult, Report
from ai_eng_audit.readiness import ReadinessResult, compute_readiness
from ai_eng_audit.strings import get as get_strings
from ai_eng_audit.tier1.billing_scan import BillingScanError, scan_billing
from ai_eng_audit.tier1.git_scan import scan_commits
from ai_eng_audit.tier1.pr_scan import PRScanError, scan_prs


_WINDOW_RE = re.compile(r"^(\d+)d$")
_DAYS_RE = re.compile(r"^(\d+)d?$")


def _window_arg(spec: str) -> AuditWindow:
    """argparse ``type=`` for --window. Raises ArgumentTypeError on bad input
    so argparse prints a clean error and exits 2 instead of a traceback."""
    m = _WINDOW_RE.match(spec)
    if not m:
        raise argparse.ArgumentTypeError(
            f"unsupported window spec: {spec!r} (use e.g. '90d')"
        )
    days = int(m.group(1))
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return AuditWindow(start=start, end=end, spec=spec)


def _days_arg(spec: str) -> int:
    """argparse ``type=`` for --revert-window / --long-lived."""
    m = _DAYS_RE.match(spec)
    if not m:
        raise argparse.ArgumentTypeError(
            f"unsupported duration: {spec!r} (use e.g. '14d' or '14')"
        )
    return int(m.group(1))


def cmd_scan(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists():
        print(f"error: {repo} is not a git repository", file=sys.stderr)
        return 1

    window: AuditWindow = args.window
    revert_window_days: int = args.revert_window
    long_lived_threshold_days: int = args.long_lived

    git_result = scan_commits(repo, window)

    errors: dict[str, str] = {}

    pr_result = None
    classifications: list = []
    if not args.no_pr:
        try:
            pr_result = scan_prs(repo, window, limit=args.pr_limit)
            classifications = classify_prs(
                pr_result.prs,
                git_result.commits,
                now=datetime.now(timezone.utc),
                revert_window_days=revert_window_days,
                long_lived_threshold_days=long_lived_threshold_days,
            )
        except PRScanError as e:
            errors["pr"] = str(e)

    billing_result: BillingScanResult | None = None
    if args.billing:
        try:
            billing_result = scan_billing(
                [Path(p) for p in args.billing], scope=args.billing_scope
            )
        except BillingScanError as e:
            errors["billing"] = str(e)

    report = Report(
        git=git_result,
        pr=pr_result,
        classifications=classifications,
        billing=billing_result,
        errors=errors,
    )

    if args.format == "json":
        _render_json(report, sys.stdout)
    else:
        _render_text(
            report,
            sys.stdout,
            no_pr=args.no_pr,
            revert_window_days=revert_window_days,
            long_lived_threshold_days=long_lived_threshold_days,
            pr_limit=args.pr_limit,
            lang=args.lang,
            annotate=args.annotate,
        )
    return 0


def _render_json(obj, out: TextIO) -> None:
    """Dump any dataclass (Report or ReadinessResult) to JSON."""

    def default(o):
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, date):
            return o.isoformat()
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, Path):
            return str(o)
        raise TypeError(f"not serializable: {type(o)}")

    json.dump(asdict(obj), out, default=default, indent=2)
    out.write("\n")


def _kv(out: TextIO, label: str, value: str) -> None:
    print(f"  {label:<28}{value}", file=out)


def _billing_total(billing: BillingScanResult, window: AuditWindow) -> Decimal:
    start_d = window.start.date()
    end_d = window.end.date()
    return sum(
        (p.cost_usd for p in billing.periods if start_d <= p.date < end_d),
        Decimal("0"),
    )


def _billing_sentence(
    billing: BillingScanResult, total: Decimal, s: Mapping[str, str]
) -> str:
    vendors = ", ".join(billing.vendors)
    key = {
        "mismatch": "h_spend_mismatch",
        "partial": "h_spend_partial",
        "aligned": "h_spend_aligned",
    }[billing.scope]
    return s[key].format(total=total, vendors=vendors)


def _render_spend_section(
    out: TextIO, billing: BillingScanResult, window: AuditWindow
) -> None:
    start_d = window.start.date()
    end_d = window.end.date()
    in_window = [p for p in billing.periods if start_d <= p.date < end_d]

    print("spend:", file=out)

    monthly: dict[tuple[int, int], Decimal] = defaultdict(lambda: Decimal("0"))
    for p in in_window:
        monthly[(p.date.year, p.date.month)] += p.cost_usd
    for (yr, mo), amount in sorted(monthly.items()):
        _kv(out, f"{yr}-{mo:02d}:", f"${amount:,.2f}")

    total = sum(monthly.values(), Decimal("0"))
    total_line = f"${total:,.2f}"
    if len(billing.vendors) > 1:
        by_vendor: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for p in in_window:
            by_vendor[p.vendor] += p.cost_usd
        breakdown = "; ".join(
            f"{v} ${by_vendor[v]:,.2f}" for v in sorted(by_vendor)
        )
        total_line = f"{total_line}  ({breakdown})"
    _kv(out, "total:", total_line)
    _kv(out, "scope_alignment:", billing.scope)
    _kv(
        out,
        "sources:",
        ", ".join(p.name for p in billing.source_files),
    )
    if billing.skipped_rows:
        _kv(out, "skipped rows:", f"{billing.skipped_rows} (CSV format drift?)")


def _render_text(
    report: Report,
    out: TextIO,
    *,
    no_pr: bool,
    revert_window_days: int,
    long_lived_threshold_days: int,
    pr_limit: int,
    lang: str,
    annotate: bool,
) -> None:
    s = get_strings(lang)
    g = report.git
    pr_error = report.errors.get("pr")
    billing_error = report.errors.get("billing")
    repo_name = g.repo_path.name
    window_label = (
        f"{g.window.start.date().isoformat()} → "
        f"{g.window.end.date().isoformat()} ({g.window.spec})"
    )
    print(f"ai-eng-audit / {repo_name} / {window_label}", file=out)
    print(file=out)

    n_commits = len(g.commits)
    commit_authors = Counter(c.author_email for c in g.commits)
    n_git_authors = len(commit_authors)

    pr_available = report.pr is not None and pr_error is None and not no_pr
    n_opened = n_merged = n_in_flight = n_abandoned = 0
    n_long_lived = n_reverted = 0
    pr_authors: set = set()
    if pr_available:
        prs = report.pr.prs  # type: ignore[union-attr]
        n_opened = len(prs)
        by_state = Counter(c.ship_state for c in report.classifications)
        n_merged = by_state.get("l1_shipped", 0)
        n_in_flight = by_state.get("in_flight", 0)
        n_abandoned = by_state.get("not_l1_shipped", 0)
        tag_counts: Counter = Counter()
        for c in report.classifications:
            for tag in c.friction_tags:
                tag_counts[tag] += 1
        n_long_lived = tag_counts.get("long_lived_open", 0)
        n_reverted = tag_counts.get("reverted_within_n", 0)
        pr_authors = {pr.author_login for pr in prs if pr.author_login}

    n_pr_authors = len(pr_authors)

    billing_total = (
        _billing_total(report.billing, g.window) if report.billing else Decimal("0")
    )

    # --- Story headline ---
    sentences: list[str] = []
    if pr_available:
        sentences.append(
            s["h_authors_opened_prs"].format(
                authors=n_pr_authors, n=n_opened, window=g.window.spec
            )
        )
        if n_opened:
            resolved = n_merged + n_abandoned
            rate_scanned = (n_merged / n_opened * 100) if n_opened else 0.0
            rate_resolved = (n_merged / resolved * 100) if resolved else 0.0
            sentences.append(
                s["h_reached_branch"].format(
                    n=n_merged,
                    branch=g.default_branch,
                    scanned=rate_scanned,
                    resolved=rate_resolved,
                )
            )
        if n_abandoned:
            sentences.append(s["h_closed_no_merge"].format(n=n_abandoned))
        if n_in_flight:
            stale = (
                s["h_stale"].format(
                    n=n_long_lived, threshold=long_lived_threshold_days
                )
                if n_long_lived
                else ""
            )
            sentences.append(s["h_in_flight"].format(n=n_in_flight, stale=stale))
        sentences.append(
            s["h_explicit_revert"].format(window=revert_window_days, n=n_reverted)
        )
    else:
        sentences.append(
            s["h_git_only"].format(
                authors=n_git_authors,
                commits=n_commits,
                branch=g.default_branch,
                window=g.window.spec,
            )
        )
        if no_pr:
            sentences.append(s["h_pr_skipped"])
        elif pr_error:
            sentences.append(s["h_pr_failed"].format(error=pr_error))

    if report.billing is not None:
        sentences.append(_billing_sentence(report.billing, billing_total, s))
    elif billing_error:
        sentences.append(s["h_billing_failed"].format(error=billing_error))

    print(textwrap.fill(" ".join(sentences), width=80), file=out)
    print(file=out)

    # --- Spend (when billing loaded) ---
    if report.billing is not None:
        _render_spend_section(out, report.billing, g.window)
        print(file=out)

    # --- Throughput ---
    print("throughput:", file=out)
    if pr_available and n_opened:
        resolved = n_merged + n_abandoned
        rate_scanned = (n_merged / n_opened * 100) if n_opened else 0.0
        rate_resolved = (n_merged / resolved * 100) if resolved else 0.0
        _kv(out, "PRs opened:", str(n_opened))
        _kv(
            out,
            "PRs merged (L1 proxy):",
            f"{n_merged}  ({rate_scanned:.1f}% scanned / "
            f"{rate_resolved:.1f}% resolved)",
        )
        _kv(out, "PRs closed w/o merge:", str(n_abandoned))
        _kv(out, "PRs in flight:", str(n_in_flight))
    _kv(out, f"commits to {g.default_branch}:", str(n_commits))
    if pr_available:
        _kv(out, "unique PR authors:", str(n_pr_authors))
        _kv(out, "unique commit authors:", str(n_git_authors))
    else:
        _kv(out, "unique commit authors:", str(n_git_authors))
    if n_commits > 0 and n_git_authors > 1:
        top_n = min(5, n_git_authors)
        top_share = (
            sum(c for _, c in commit_authors.most_common(top_n)) / n_commits * 100
        )
        _kv(
            out,
            f"top-{top_n} commit share:",
            f"{top_share:.1f}% (names withheld by design)",
        )

    # --- Friction ---
    if pr_available and n_opened:
        print(file=out)
        print("friction:", file=out)
        abandoned_share = (n_abandoned / n_opened * 100) if n_opened else 0.0
        _kv(
            out,
            "abandoned:",
            f"{n_abandoned}  ({abandoned_share:.1f}% of opened)",
        )
        _kv(
            out,
            f"long-lived open > {long_lived_threshold_days}d:",
            str(n_long_lived),
        )
        _kv(
            out,
            f"explicit revert < {revert_window_days}d:",
            str(n_reverted),
        )

    # --- Commits by ISO week (supporting view) ---
    if g.commits:
        print(file=out)
        print("commits by ISO week:", file=out)
        weekly: Counter = Counter()
        for c in g.commits:
            iso = c.authored_date.isocalendar()
            weekly[(iso.year, iso.week)] += 1
        for (yr, wk), n in sorted(weekly.items()):
            print(f"  {yr}-W{wk:02d}  {n}", file=out)

    # --- Partial-scan warning ---
    if pr_available and report.pr is not None and report.pr.truncated:
        print(file=out)
        print(s["w_partial_pr"].format(limit=pr_limit), file=out)

    # --- Annotations (opt-in via --annotate) ---
    if annotate:
        annotations = compute_annotations(
            report, g.window, pr_available=pr_available
        )
        if annotations:
            print(file=out)
            print(s["a_section_header"], file=out)
            for a in annotations:
                print("  • " + s[a.key].format(**a.values), file=out)

    # --- Footer ---
    print(file=out)
    print("—", file=out)
    print(s["f_methodology"].format(version=report.methodology_version), file=out)
    print(s["f_disclaimer"], file=out)


def cmd_readiness(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    if not repo.exists():
        print(f"error: {repo} does not exist", file=sys.stderr)
        return 1

    result = compute_readiness(repo)

    if args.format == "json":
        _render_json(result, sys.stdout)
    else:
        _render_readiness_text(result, sys.stdout, lang=args.lang)
    return 0


def _render_readiness_text(
    result: ReadinessResult, out: TextIO, *, lang: str
) -> None:
    s = get_strings(lang)
    repo_name = result.repo_path.name
    print(s["r_title"].format(repo=repo_name), file=out)
    print(file=out)

    # Group checks by category, preserving order of first appearance
    grouped: dict[str, list] = {}
    for check in result.checks:
        grouped.setdefault(check.category, []).append(check)

    for category, items in grouped.items():
        header_key = f"r_cat_{category}"
        print(s.get(header_key, category + ":"), file=out)
        for check in items:
            mark = "✓" if check.present else "✗"
            label = s.get(f"r_chk_{check.key}", check.key)
            suffix = f"  ({check.found_at})" if check.found_at else ""
            print(f"  {mark} {label}{suffix}", file=out)
        print(file=out)

    print("—", file=out)
    print(textwrap.fill(s["r_footer"], width=80), file=out)


def main() -> int:
    parser = argparse.ArgumentParser(prog="ai-eng-audit")
    sub = parser.add_subparsers(dest="cmd", required=True)

    scan = sub.add_parser(
        "scan", help="scan a git repo's commit + PR history with optional AI billing"
    )
    scan.add_argument("--repo", default=".", help="path to git repo (default: cwd)")
    scan.add_argument(
        "--window",
        type=_window_arg,
        default="90d",
        help="audit window (default: 90d)",
    )
    scan.add_argument(
        "--format", choices=("text", "json"), default="text", help="output format"
    )
    scan.add_argument(
        "--lang",
        choices=("en", "zh"),
        default="en",
        help=(
            "language for narrative text and footer (default: en). "
            "Section labels, metric names, and technical terms (PR, L1, branch, "
            "scope_alignment, etc.) stay English in every locale."
        ),
    )
    scan.add_argument(
        "--revert-window",
        type=_days_arg,
        default="14d",
        help="window N for explicit reverted-within-N (default: 14d, per methodology)",
    )
    scan.add_argument(
        "--long-lived",
        type=_days_arg,
        default="30d",
        help="threshold for long-lived open PR (default: 30d, per methodology)",
    )
    scan.add_argument(
        "--no-pr",
        action="store_true",
        help="skip the GitHub PR scan (git history only)",
    )
    scan.add_argument(
        "--pr-limit",
        type=int,
        default=1000,
        help="max PRs to fetch from the GitHub API (default: 1000)",
    )
    scan.add_argument(
        "--billing",
        action="append",
        default=[],
        help=(
            "path to an AI vendor billing CSV (Anthropic Console cost CSV / "
            "OpenRouter activity CSV). Pass multiple times to load several files. "
            "Caller is responsible for non-overlapping scopes; see "
            "docs/methodology.md."
        ),
    )
    scan.add_argument(
        "--billing-scope",
        choices=("aligned", "partial", "mismatch"),
        default="mismatch",
        help=(
            "declared alignment between billing and throughput scope "
            "(default: mismatch). 'aligned' = billing limited to scanned repo(s); "
            "'partial' = billing is a superset; 'mismatch' = billing is org-level."
        ),
    )
    scan.add_argument(
        "--annotate",
        action="store_true",
        help=(
            "append a 'notable contrasts' section: derived observations "
            "(WIP delta, contributor concentration, merge throughput, spend "
            "pairing) computed from fields already in the report. No external "
            "benchmarks, no good/bad labels. See docs/methodology.md."
        ),
    )
    scan.set_defaults(func=cmd_scan)

    readiness = sub.add_parser(
        "readiness",
        help=(
            "check whether a repo has the shared context an AI agent needs "
            "(CI / tests / docs / CODEOWNERS / PR template / etc.). "
            "Presence checklist, not a score; reads file existence only."
        ),
    )
    readiness.add_argument(
        "--repo", default=".", help="path to repo (default: cwd)"
    )
    readiness.add_argument(
        "--format", choices=("text", "json"), default="text", help="output format"
    )
    readiness.add_argument(
        "--lang",
        choices=("en", "zh"),
        default="en",
        help="language for category labels and footer (default: en)",
    )
    readiness.set_defaults(func=cmd_readiness)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
