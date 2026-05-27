"""Localized string templates for CLI text output.

Translation policy: loose. Section labels, metric names, technical terms
(``PR``, ``main``, ``branch``, ``scope_alignment``, ``L1``, ``ship rate``,
``in flight``, ``scanned``, ``resolved`` etc.) stay English in every locale.
Only narrative sentences, warnings, and footer prose are localized.
This prioritizes fast engineering comprehension over full translation.

To add a locale, copy ``EN`` and translate the values. Keys must match.
"""

from __future__ import annotations

from typing import Mapping


EN: Mapping[str, str] = {
    # Headline — PR-mode
    "h_authors_opened_prs": (
        "{authors} authors opened {n} PRs over {window}."
    ),
    "h_reached_branch": (
        "{n} reached `{branch}` "
        "({scanned:.1f}% of scanned, {resolved:.1f}% of resolved)."
    ),
    "h_closed_no_merge": "{n} closed without merging.",
    "h_in_flight": "{n} still in flight{stale}.",
    "h_stale": " — {n} open > {threshold}d",
    "h_explicit_revert": "Explicit revert <{window}d: {n}.",
    # Headline — git-only mode
    "h_git_only": (
        "{authors} authors landed {commits} commits on `{branch}` over {window}."
    ),
    "h_pr_skipped": "PR scan skipped (--no-pr).",
    "h_pr_failed": "PR scan failed: {error}.",
    # Headline — billing
    "h_spend_aligned": "AI spend ${total:,.2f} ({vendors}).",
    "h_spend_partial": "Partial-scope AI spend ${total:,.2f} ({vendors}).",
    "h_spend_mismatch": (
        "Org-level AI spend ${total:,.2f} ({vendors}); "
        "throughput is repo-level (scope mismatch)."
    ),
    "h_billing_failed": "Billing scan failed: {error}.",
    # Warning + footer
    "w_partial_pr": (
        "partial PR scan: hit --pr-limit={limit}; "
        "some window-overlapping PRs may be missing."
    ),
    "f_methodology": (
        "methodology {version}. definitions in docs/methodology.md."
    ),
    "f_disclaimer": (
        "workflow signals only; not personnel evaluation. "
        "Tier 2 per-PR AI attribution arrives in later versions."
    ),
    # Annotations (--annotate)
    "a_section_header": "notable contrasts:",
    "a_wip_change": (
        "in-window flow: {sign}{n} net "
        "({opened} PRs created in window, {resolved} PRs closed in window; "
        "distinct from 'PRs opened' above, which counts any window-overlapping PR)"
    ),
    "a_contributor_concentration": (
        "top-{top_n} of {total} authors produced {pct:.1f}% of commits "
        "({author_pct:.0f}% of authors → ~{pct:.0f}% of work)"
    ),
    "a_merge_velocity": (
        "merge throughput: {merged} merged over {days}d ≈ {per_day:.2f} PRs/day"
    ),
    "a_spend_per_pr_aligned": (
        "AI spend per merged PR: ${total:,.2f} / {merged} = ${per_pr:,.2f}"
    ),
    "a_spend_pairing_unaligned": (
        "AI spend ${total:,.2f} vs {merged} merged PRs "
        "(per-PR cost not computed: scope_alignment = {scope})"
    ),
    # Readiness checklist
    "r_title": "ai-eng-audit / {repo} / readiness checklist",
    "r_footer": (
        "this is a presence checklist, not a score. agents work more reliably "
        "in repos with shared context (CI, tests, ownership, docs); missing "
        "items don't block AI usage but do make AI output harder to review, "
        "test, and recover from."
    ),
    "r_cat_ci_testing": "CI / testing:",
    "r_cat_documentation": "documentation:",
    "r_cat_collaboration": "collaboration flow:",
    "r_cat_config_security": "config / security:",
    "r_chk_ci_workflow": "CI workflow",
    "r_chk_tests_dir": "tests directory",
    "r_chk_lint_config": "lint / formatter config",
    "r_chk_readme": "README",
    "r_chk_contributing": "CONTRIBUTING guide",
    "r_chk_license": "LICENSE",
    "r_chk_codeowners": "CODEOWNERS",
    "r_chk_pr_template": "PR template",
    "r_chk_gitignore": ".gitignore",
    "r_chk_env_example": ".env example",
}


ZH: Mapping[str, str] = {
    # Headline — PR-mode
    "h_authors_opened_prs": "过去 {window},{authors} 人提了 {n} 个 PR。",
    "h_reached_branch": (
        "{n} 个进了 `{branch}`"
        "({scanned:.1f}% scanned / {resolved:.1f}% resolved)。"
    ),
    "h_closed_no_merge": "{n} 个开了又关没合。",
    "h_in_flight": "{n} 个还在 in flight{stale}。",
    "h_stale": ",其中 {n} 个开了 {threshold}d+",
    "h_explicit_revert": "Explicit revert <{window}d:{n}。",
    # Headline — git-only mode
    "h_git_only": (
        "过去 {window},{authors} 人在 `{branch}` 上合了 {commits} 个 commit。"
    ),
    "h_pr_skipped": "PR scan 已跳过 (--no-pr)。",
    "h_pr_failed": "PR scan 失败:{error}。",
    # Headline — billing
    "h_spend_aligned": "AI 支出 ${total:,.2f}({vendors})。",
    "h_spend_partial": "Partial-scope AI 支出 ${total:,.2f}({vendors})。",
    "h_spend_mismatch": (
        "Org 级 AI 支出 ${total:,.2f}({vendors});"
        "throughput 是 repo 级(scope mismatch)。"
    ),
    "h_billing_failed": "Billing scan 失败:{error}。",
    # Warning + footer
    "w_partial_pr": (
        "PR scan 部分截断:触顶 --pr-limit={limit},"
        "window 内可能有 PR 漏扫。"
    ),
    "f_methodology": (
        "methodology {version}。定义见 docs/methodology.md。"
    ),
    "f_disclaimer": (
        "工作流信号,非个人评估。"
        "Tier 2 per-PR AI 归因后续版本接入。"
    ),
    # Annotations (--annotate)
    "a_section_header": "几个值得注意的对比:",
    "a_wip_change": (
        "window 内 PR 流量:{sign}{n} 净变化"
        "({opened} 个 window 内创建,{resolved} 个 window 内关闭;"
        "与上方 'PRs opened' 口径不同——后者包括所有与 window 重叠的 PR)"
    ),
    "a_contributor_concentration": (
        "top-{top_n} / {total} 个 author 贡献了 {pct:.1f}% commits"
        "({author_pct:.0f}% 的人 → ~{pct:.0f}% 的工作量)"
    ),
    "a_merge_velocity": (
        "merge 吞吐:{merged} 个 merged / {days}d ≈ {per_day:.2f} PR/天"
    ),
    "a_spend_per_pr_aligned": (
        "AI 支出 / merged PR:${total:,.2f} / {merged} = ${per_pr:,.2f}"
    ),
    "a_spend_pairing_unaligned": (
        "AI 支出 ${total:,.2f} vs {merged} 个 merged PR"
        "(per-PR cost 不计算:scope_alignment = {scope})"
    ),
    # Readiness checklist
    "r_title": "ai-eng-audit / {repo} / readiness checklist",
    "r_footer": (
        "这是 presence checklist,不是评分。Agent 在共享上下文充足(CI、tests、"
        "ownership、docs)的 repo 里工作更可靠;缺项不阻塞 AI 使用,但会让 AI 产出"
        "更难 review、test、回滚。"
    ),
    "r_cat_ci_testing": "CI / 测试:",
    "r_cat_documentation": "文档:",
    "r_cat_collaboration": "协作流程:",
    "r_cat_config_security": "配置 / 安全:",
    "r_chk_ci_workflow": "CI workflow",
    "r_chk_tests_dir": "tests 目录",
    "r_chk_lint_config": "lint / formatter 配置",
    "r_chk_readme": "README",
    "r_chk_contributing": "CONTRIBUTING 指南",
    "r_chk_license": "LICENSE",
    "r_chk_codeowners": "CODEOWNERS",
    "r_chk_pr_template": "PR template",
    "r_chk_gitignore": ".gitignore",
    "r_chk_env_example": ".env example",
}


STRINGS: Mapping[str, Mapping[str, str]] = {"en": EN, "zh": ZH}


def get(lang: str) -> Mapping[str, str]:
    """Return the string table for ``lang``; fall back to ``en``."""
    return STRINGS.get(lang, EN)
