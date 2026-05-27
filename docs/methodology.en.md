# Methodology

Two things that companies usually measure separately, put on one chart:

1. AI tool spend
2. Engineering throughput — the rate at which code reaches a "shipped" state

The tool does not compute ROI. It puts the two curves side by side. The rest of this document defines each v1.0 metric and its known limits.

The tool runs locally and reads git history, PR API metadata, and a vendor billing CSV you provide. It does not read code content, PR / issue bodies, comment bodies, or prompts; it does read changed file paths, diff stats, and review / comment event metadata (timestamp, author handle, bot flag).

_"headline" in this document means the default summary numbers at the top of a report._

## "Shipped"

"Shipped" means merged to the default branch (L1). It's a useful proxy but not equivalent to release, nor to customer-visible value. Every "shipped" figure in a report carries the `(L1 proxy)` suffix. L2 (release tag / changelog / deployment record) and L3 (customer-visible) require per-company CI/CD or feature-flag integration; not in v1.0.

## Signals

Each PR has one ship_state (**shipped** / **in-flight** / **ambiguous**) and may carry one or more friction tags — a reverted PR is both shipped and tagged. v1.0 ships three friction tags:

**Abandoned** — opened then closed without merging. Closing exploratory work or duplicates is fine; the tool does not distinguish those from "got stuck", it just counts closures.

**Reverted within N** (default N=14 days) — v1.0 detects **explicit reverts only**: a commit whose message starts with `Revert "..."` and matches the title of a merged PR. **Known blind spots**: squash-merged reverts, non-standard subject formats, cross-repo reverts, and partial reverts are not detected. So this count is a **lower bound**, not a true revert volume.

**Long-lived open** — non-draft PRs open more than 30 days (default, CLI configurable). The report also gives the median and p90 of "actual open days at close" so 30 can be judged in context.

All thresholds are CLI-configurable; the report header lists the active values.

## Spend ↔ Throughput

AI spend and L1 throughput aligned on monthly buckets. **No PR-level attribution** — mainstream vendors' monthly billing CSVs don't have that granularity.

### Supported billing CSV sources

| Vendor | File | What we read |
|---|---|---|
| `anthropic` | Anthropic Console **cost** export (rows include `cost_usd`) | `usage_date_utc` + `cost_usd`, summed per day |
| `openrouter` | OpenRouter Activity export (`Date,Slug,Usage,BYOK Usage,...`) | `Date` + `Usage`, summed per day. **`BYOK Usage` excluded** — BYOK traffic is not billed by OpenRouter |

The Anthropic Console **tokens** export (token counts only, no USD) is explicitly rejected with a message telling the caller to use the cost CSV instead.

**Header drift detection**: when a CSV yields zero parseable rows alongside non-zero skipped rows, the tool raises `BillingScanError` rather than silently emitting $0.00 — this protects against vendor CSV format drift. Non-zero skipped counts surface in the spend section.

**Multiple files**: `--billing` can be repeated. Each file is detected by vendor and parsed independently; days are kept distinct per vendor before being summed.

**Double-count caveat** (caller's responsibility): if two vendor CSVs sit in a proxy relationship — typical case: OpenRouter forwarding requests to Anthropic while you also load the Anthropic Console direct invoice — the tool will double-count. It does not de-duplicate; file scope is the caller's call.

### Scope alignment

Every report header stamps a `scope_alignment` value describing how the billing scope relates to the throughput scan scope:

| Value | Meaning | Headline phrasing |
|---|---|---|
| `aligned` | Billing scope matches the throughput scan scope (per-team billing, or single-repo company) | `AI spend $X (vendors)` |
| `partial` | Billing covers a superset of throughput; partial attribution possible (per-team billing but only some of the team's repos scanned) | `Partial-scope AI spend $X (vendors)` |
| `mismatch` | Billing is org-level total, throughput is repo / path level; not the same population | `Org-level AI spend $X (vendors); throughput is repo-level (scope mismatch)` |

In `mismatch` mode the headline must use the "org-level vs repo-level" phrasing; the tool does not compute per-PR cost. The reader gets two parallel trends and judges for themselves.

## Known biases

A few common reasons numbers will diverge from intuition:

**Billing data lag** — monthly billing settles only after the period closes. The most recent month's spend often looks artificially low because the export was generated mid-period.

**AI tool coverage** — the tool only sees the billing CSVs you provide. Copilot inline suggestions, cloud-only agents, and IDE plugins without an export are invisible. This is a capability boundary, not an implicit signal.

**Merge strategy distorts author metadata** — squash collapses multiple authors into one; cherry-pick credits the picker; rebase rewrites author metadata. This distorts commit counts, top-N author share, and unique commit-author counts. The tool does not compensate.

**PR count / batching** — AI may shift PR shape: fewer larger PRs, or more smaller ones. Throughput counted in PRs moves with shape regardless of actual work volume. The headline remains PR-count-based.

**Seat licensing distorts spend** — some vendors report spend based on seats purchased, not actual usage. A team paying for 100 seats with 30 active users will show inflated spend-per-throughput.

**Research / exploratory work mis-counted as friction** — PRs abandoned for exploratory reasons land in the abandoned count; the tool does not distinguish "exploratory closure" from "stuck and abandoned". R&D-heavy teams will appear to have inflated abandoned counts.

**Calendar / release cadence** — company freezes, release trains, and on-call rotations distort monthly buckets. A freeze month shows artificially low throughput; the month after appears artificially high — unrelated to AI. The tool does not auto-detect organizational calendars.

**Team capacity** — hiring, attrition, layoffs, re-orgs, and parental leave shift capacity independently of AI tooling. Throughput moves may come purely from headcount changes. The tool does not model headcount.

## Notable contrasts (`--annotate`)

`--annotate` appends a `notable contrasts:` section to the report containing a few observations **derived strictly from fields already shown in the report**. **No external benchmarks, no "healthy / unhealthy" labels, no prescriptive recommendations** — the goal is to surface contrasts a reader might miss, while the reader does the judging.

Definitions:

| Item | Algorithm | Shown when |
|---|---|---|
| **in-window flow** | (count of PRs whose `created_at` is in window) − (count of PRs whose `closed_at` is in window) = net delta | PR scan succeeded and not `--no-pr` |
| **contributor concentration** | `top-N commit share` + `top-N as % of all authors` (same N, two angles) | git commits exist and author count > 1 |
| **merge throughput** | merged PRs / window days = average per day | merged > 0 |
| **spend pairing** | When `scope_alignment = aligned`: billing total / merged = per-PR cost. Otherwise: show spend and merged side by side; decline to compute the per-PR ratio | `--billing` loaded and merged > 0 |

**Denominator clash with elsewhere-in-report numbers:**
- `in-window flow` uses "PRs whose state change happened in window"; the throughput section's `PRs opened` counts any window-overlapping PR (different denominator)
- `spend pairing` refuses the per-PR ratio under mismatch / partial scope because spend and merged come from different populations

These are facts about the data, computed from the data. The reader still does the judging.

---

## What the numbers don't mean

Per-author breakdowns exist, but author outliers dominate small aggregates; these numbers should not feed performance, compensation, hiring, firing, or RIF decisions. The trends are correlations, not causes — "AI spend grew faster than shipped PRs" describes two trends, not a causal relationship.

Teams that have restructured around AI agents — fewer PRs, larger semantic changes per commit, bypassing the PR flow — will look unproductive in this tool. The methodology best fits organizations of 30 to 5,000 engineers using conventional GitHub / GitLab PR flow.

Distributed under MIT License. Not legal, financial, or HR advice. Reports are provided as-is; authors decline responsibility for decisions made on their basis.

## Reproducibility

Every spend figure can be reconciled against the vendor's billing console — within rounding, currency, discount, tax, and export-scope differences.

`tests/` contains synthetic fixtures exercising the friction classifier, billing parsers, and annotations modules; `python -m unittest discover` passes before each release. **v1.0 does not ship a public-OSS-corpus gold set with precision/recall figures** — that's planned for v1.x+.

Every report stamps `methodology-version: vX.Y`. Current: v1.0.

## Future work

Not in v1.0 but on the roadmap:

- Tier 2 per-PR AI attribution (attribute local AI session logs to specific PRs)
- Additional friction sub-tags (abandoned-with-replacement, reverted-then-fixed, review latency, closed-without-merge issues)
- L2 / L3 ship detection (release tag / deployment record / customer-visible event)
- Public gold-set + precision/recall figures
- Prior-period trend Δ%

Progress tracked in [GitHub Issues](https://github.com/0error-ob/ai-eng-audit/issues).
