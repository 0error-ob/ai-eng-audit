# 方法论

把 AI 支出和工程吞吐放到同一张图上。不算 ROI,只做可见性。

工具本地运行,读 git 历史、PR API 元数据、用户提供的厂商 billing CSV。不读代码内容、PR / issue 正文、评论正文、prompts;会读取 changed file paths、diff stats、review / comment 事件元数据(时间戳、author handle、bot 标记)。

_本文档里 "headline" 指报告顶部默认汇总数字。_

## "Shipped"

"Shipped" 指合并到主分支(L1)。它是个好用的代理,但不等同 release,也不等同客户可见。报告里每个 "shipped" 数字后面都带 `(L1 proxy)`。L2(进 release tag / changelog / 部署记录)和 L3(到生产 + 客户可见)需要逐公司接入 CI/CD 或 feature flag 系统,没有通用 API,不在 v1.0 范围。

## 信号

每个 PR 有一个 ship_state(**已 ship** / **在途** / **模糊**),并可附加一组 friction tag——reverted PR 同时是已 ship 与带 friction tag。v1.0 实现三个 friction tag:

**Abandoned** —— 开了又关、没 merge。关闭探索性工作或重复 PR 是好事——本工具不区分两者,只报关闭计数。

**Reverted within N**(默认 N=14 天) —— v1.0 只识别**显式 revert**:commit 消息以 `Revert "..."` 起头并对应到一个 merged PR 的 title。**已知盲点**:squash-merge 吃掉的 revert、非标准 subject 的 revert、跨 repo revert、partial revert 都识别不到——所以这个数字是**下界**,不是真实回滚量。

**Long-lived open** —— 开放超过 30 天(默认,CLI 可改)的非 draft PR。报告同时给"实际关闭时 open 天数"的中位数和 p90,让读者判断 30 天对自家是否反常。

所有阈值在 CLI 可改;报告 header 列出当前生效值。

## Spend ↔ Throughput

把 AI spend 和 L1 throughput 按月对齐。**不做 PR 级归因**——主流厂商月度 billing CSV 没有这种粒度。

### 支持的 billing CSV 来源

| Vendor | 文件来源 | 我们读什么 |
|---|---|---|
| `anthropic` | Anthropic Console 的 **cost** export(每行带 `cost_usd`) | `usage_date_utc` + `cost_usd`,按日聚合 |
| `openrouter` | OpenRouter Activity export(`Date,Slug,Usage,BYOK Usage,...`) | `Date` + `Usage`,按日聚合。**`BYOK Usage` 不计入**(自带 key 流量,OpenRouter 不收钱) |

Anthropic Console 的 **tokens** export(只有 token 计数无 USD)会被工具明确拒绝,提示用户改用 cost CSV。

**Header drift 检测**:某份 CSV 解析出零条有效行但有跳过行时,工具直接 `BillingScanError`——避免 vendor 改字段名导致静默 $0.00 输出。非零跳过数显式标在报告 spend section。

**多文件支持**:`--billing` 可以重复指定。各文件按 vendor 独立解析、按日合并。

**双计 caveat**(用户责任):如果两个 vendor CSV 存在代理关系(典型场景:OpenRouter 转发请求到 Anthropic,而你又同时 load Anthropic Console 的直接账单),会 double-count。工具不做去重——文件 scope 由调用方决定。

### Scope alignment

每份报告 header 必须标 `scope_alignment`,描述 billing 范围与 throughput 扫描范围的关系:

| 值 | 含义 | Headline 措辞 |
|---|---|---|
| `aligned` | Billing 已限定到 throughput 扫描的同一组 repo / team(per-team billing,或单 repo 公司) | `AI spend $X (vendors)` |
| `partial` | Billing 是 throughput 的超集,部分可归因(per-team billing 但只扫了 team 内一部分 repo) | `Partial-scope AI spend $X (vendors)` |
| `mismatch` | Billing 是 org 级总账,throughput 是 repo / path 级,不是同一总体 | `Org-level AI spend $X (vendors); throughput is repo-level (scope mismatch)` |

`mismatch` 模式下,headline 必须用 "org-level vs repo-level" 措辞,工具不省略范围差。这意味着 mismatch 模式下**报告不替读者算 per-PR cost**——读者拿到两条并列趋势,自行判断。

## 已知偏差

读报告前,几个会让数字偏离直觉的常见原因:

**Billing 数据延迟** —— 月度 billing 在账期关闭后才结算。最近一个月的 spend 通常显得偏低,只因为导出时点在期中。

**AI 工具覆盖** —— 工具只读你提供的 billing CSV。Copilot inline、纯云端 agent、无导出能力的 IDE 插件的 spend 看不到。这不是隐含信号,是工具能力边界。

**Merge 策略影响 author 元数据** —— Squash 把多 author 合并成一个;cherry-pick 把功劳归给挑选者;rebase 重写 author 元数据。这会扭曲 commit 计数、top-N 作者占比、unique commit author 数。工具不补偿。

**PR 数量 / batching** —— AI 可能让 PR 变得更大更少或更小更多。以 PR 数为单位的 throughput 会随 PR 形态变化升降,与实际工作量无关。headline 仍按 PR 数。

**Seat-license 影响 spend** —— 部分厂商按购买的 seat 数计 spend,不是按实际用量。100 座 30 人用的团队会算出虚高的 spend-per-throughput。

**研究 / 探索工作被误判摩擦** —— 为探索而 abandoned 的 PR 会落进 abandoned 计数,工具不区分"探索性废弃"和"卡住废弃"。R&D 比重大的团队会显得 abandoned 偏高。

**日历 / release 周期** —— 公司停工、release train、on-call 轮值扭曲月桶。停工月吞吐偏低、后一月人为偏高,与 AI 无关。工具不自动检测组织日历。

**Team capacity** —— 招聘、流失、裁员、reorg、产育假独立于 AI 改变团队产能。吞吐升降可能纯粹来自人数变动。工具不建模 headcount。

## Notable contrasts(`--annotate`)

`--annotate` 选项在报告末尾插一段 `notable contrasts:`,放几条**完全由报告内已有字段派生**的观察。**不引入外部 benchmark,不打"健康/不健康"标签,不给行动建议**——只把容易被读者忽略的对比显式列出来。

定义:

| 项 | 算法 | 显示条件 |
|---|---|---|
| **in-window flow** | (PR.created_at 在 window 内的计数) − (PR.closed_at 在 window 内的计数)= 净变化 | PR scan 成功且非 `--no-pr` |
| **contributor concentration** | `top-N 的 commit 占比` + `top-N 占总 author 数的百分比`(同一个 top-N 数,两边视角并列) | git commits 存在且 author > 1 |
| **merge throughput** | merged PR 数 / window 天数 = 日均 | merged > 0 |
| **spend pairing** | 当 `scope_alignment = aligned`:billing total / merged = per-PR cost;否则只并列展示 spend 与 merged 数,不计算 per-PR ratio | 加载了 `--billing` 且 merged > 0 |

**与已展示数据的口径区别**:
- `in-window flow` 用的是 "PR 在 window 内被创建/关闭" 的计数,跟 throughput section 里 `PRs opened`(window-overlapping 任何一类)**不是同一个分母**
- `spend pairing` 在 mismatch / partial 模式下**拒绝**计算 per-PR cost,因为 spend 和 merged 来自不同 population

读者拿到这几条:**自己判断**这些对比意味着什么。

---

## 数字不代表什么

按 author 拆分的数字存在,但小样本下个人异常值主导聚合。这些数字不应进绩效、薪酬、招聘、解雇、裁员决策。趋势是相关性不是因果——"AI spend 涨得比 shipped PR 快" 描述两条趋势的关系,不证明 AI 工具导致 gap,也不证明某团队该负责。

围绕 AI agent 重新设计工作流的小团队(PR 变少、单 commit 语义改动变大、绕过 PR)在工具里会显得"不出活"。这套方法论最适合 30–5000 工程师、使用传统 GitHub / GitLab PR 流的组织。

按 MIT License 分发。不构成法律、财务、HR 建议;报告 as-is,作者不对基于报告作出的决策负责。

## 可复现性

每个 spend 数字都可对照厂商 billing console 核对,在 rounding、汇率、折扣、税、export 口径的差异范围内。

`tests/` 目录里有合成 fixtures 跑 friction classifier / billing parser / annotations 三个模块,每次发版前 `python -m unittest discover` 通过。**v1.0 不包含基于公开 OSS repo 的 gold-set + precision/recall 数据集**——这是 v1.x+ 的事。

每份报告 stamp `methodology-version: vX.Y`。当前 v1.0。

## 未来工作

不在 v1.0 范围、但已经在 roadmap 上的:

- Tier 2 per-PR AI attribution(把 AI session log 归因到具体 PR)
- 更多 friction 子分类(abandoned-with-replacement、reverted-then-fixed、review latency、closed-without-merge issue)
- L2 / L3 ship 检测(release tag / deployment record / customer-visible event)
- 公开 gold-set + precision/recall 数据集
- 跨 prior-period 的 trend Δ%

进度跟 [GitHub Issues](https://github.com/0error-ob/ai-eng-audit/issues)。
