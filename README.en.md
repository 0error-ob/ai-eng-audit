# AI Eng Audit

Plot AI tool spend against engineering throughput on a shared chart. Local, open-source, one command.

## What it is

Over the last year a lot of teams burned real money on Claude, Cursor, Copilot, and the rest. The invoices are clear; the output is not.

The tool reads your local git history, PR data, and (optionally) the billing CSV you export from your AI vendor, putting spend and shipped output on the same timeline. You see:

- total AI spend over the window, broken out by month
- PRs merged to the default branch and the L1 ship rate
- PRs opened and then closed, merged and then reverted, or open for too long

## How to use it

```bash
export GITHUB_TOKEN=ghp_xxxxx
pip install ai-eng-audit
ai-eng-audit scan --repo /path/to/your/repo --window 90d --annotate \
    --billing ~/Downloads/anthropic_cost.csv \
    --billing ~/Downloads/openrouter_activity.csv
```

Python 3.11+. Generate a `GITHUB_TOKEN` PAT at https://github.com/settings/tokens with `repo` scope.

Add `--lang zh` for Chinese narrative; section labels, metric names, and technical terms (PR, L1, `scope_alignment`, etc.) stay English in both locales.

`--billing` can be repeated. Currently supports the Anthropic Console **cost** export and the OpenRouter Activity export (auto-detected by header). Omit `--billing` to get the git + PR report only.

`--annotate` appends a `notable contrasts:` block with a few derived observations (in-window flow, contributor concentration, merge throughput, spend pairing) computed strictly from numbers already in the report. No external benchmarks, no healthy/unhealthy labels.

Add `--format json` for JSON output. Metric definitions, supported vendors, scope-alignment rules, and annotation algorithms are in [docs/methodology.en.md](docs/methodology.en.md).

## What the report looks like

A run looks roughly like this (numbers are synthetic):

```
ai-eng-audit / your-repo / 2026-02-26 → 2026-05-27 (90d)

10 authors opened 187 PRs over 90d. 142 reached `main` (75.9% of scanned, 84.0%
of resolved). 27 closed without merging. 18 still in flight — 4 open > 30d.
Explicit revert <14d: 2. Org-level AI spend $4,231.50 (anthropic, openrouter);
throughput is repo-level (scope mismatch).

spend:
  2026-03:                    $1,124.00
  2026-04:                    $1,572.30
  2026-05:                    $1,535.20
  total:                      $4,231.50  (anthropic $1,387.10; openrouter $2,844.40)
  scope_alignment:            mismatch
  sources:                    anthropic_cost.csv, openrouter_activity.csv

throughput:
  PRs opened:                 187
  PRs merged (L1 proxy):      142  (75.9% scanned / 84.0% resolved)
  PRs closed w/o merge:       27
  PRs in flight:              18
  commits to main:            312
  unique authors:             10
  top-5 commit share:         72.3% (names withheld by design)

friction:
  abandoned:                  27  (14.4% of opened)
  long-lived open > 30d:      4
  explicit revert < 14d:      2

commits by ISO week:
  2026-W09  18
  2026-W10  25
  2026-W11  32
  2026-W12  29
  2026-W13  21
  2026-W14  18
  2026-W15  24
  2026-W16  31
  2026-W17  28
  2026-W18  35
  2026-W19  26
  2026-W20  19
  2026-W21  6

notable contrasts:
  • in-window flow: +5 net (165 PRs created in window, 160 PRs closed in window; distinct from 'PRs opened' above, which counts any window-overlapping PR)
  • top-5 of 10 authors produced 72.3% of commits (50% of authors → ~72% of work)
  • merge throughput: 142 merged over 90d ≈ 1.58 PRs/day
  • AI spend $4,231.50 vs 142 merged PRs (per-PR cost not computed: scope_alignment = mismatch)

—
methodology v1.0. definitions in docs/methodology.md.
workflow signals only; not personnel evaluation. Tier 2 per-PR AI attribution arrives in later versions.
```
