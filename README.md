# AI Eng Audit

这个项目让你直观感受 AI 支出和工程上线，以及你的工程系统能不能安全接住更多 AI 生成的代码。本地、开源、两个命令。

## 它是什么

过去一年很多团队在 Claude / Cursor / Copilot 这些工具上烧了不少钱，账单清清楚楚，但产出说不清楚。

**`ai-eng-audit scan`** 读你本地的 git 历史、PR 数据，以及（可选）AI 厂商账单 CSV，把"烧了多少钱"和"上线了多少代码"对到同一根时间轴上。能看到：

- 这几个月 AI 花费的总额和按月分布
- 同期合并到主分支的 PR 数量、ship rate (L1)
- 哪些 PR 开了又关、合了又被回滚、开太久没合

**`ai-eng-audit readiness`** 不算账单，只看你 repo 里有没有 agent 协作需要的基础设施(CI、tests、CODEOWNERS、PR template 等)。类比 PC 时代:单机 PC 的 ROI 不明显,LAN 铺开后组织效率才显现。Agent 也一样,单个工程师提速 ≠ 团队产出提升,真正的"AI LAN"是 repo 里有足够共享上下文让 agent 可靠工作。这条命令告诉你你的 repo 在不在位。

## 怎么用

```bash
export GITHUB_TOKEN=ghp_xxxxx
pip install ai-eng-audit

# audit: AI 支出 vs 工程产出
ai-eng-audit scan --repo /path/to/your/repo --window 90d --lang zh --annotate --risk \
    --billing ~/Downloads/anthropic_cost.csv \
    --billing ~/Downloads/openrouter_activity.csv

# readiness: agent 协作基础设施 checklist
ai-eng-audit readiness --repo /path/to/your/repo --lang zh
```

Python 3.11+。`GITHUB_TOKEN` 在 https://github.com/settings/tokens 生成 PAT，scope 勾 `repo`。

`--lang zh` 让叙述句子和 footer 用中文;section 名、metric 名、技术术语(PR、L1、scope_alignment 等)在两种语言下都保持英文。不传 `--lang` 默认是英文。

`--billing` 可重复传多个文件，支持 Anthropic Console **cost** export 和 OpenRouter Activity export(自动按 header 识别)。不传 `--billing` 就只跑 git + PR 部分。

`--annotate` 在报告末尾插一段 `notable contrasts:`,放几条从报告自身数据派生的对比(in-window flow / contributor concentration / merge throughput / spend pairing)。不引入外部 benchmark,不打健康/不健康标签。

`--risk` 在报告末尾插一段 `maintainability risk signals:`,放三组 pattern:**file churn hotspot**(窗口内被改最多的文件)、**post-merge fix burst**(merge 后 7 天内同文件被再次 commit 的次数)、**revert rate by month**。读 commit 的 changed file path,不读 file content;不出 score,不打健康标签。

加 `--format json` 出 JSON。指标定义、支持的 vendor、scope alignment、annotation / risk 算法、readiness 规则全在 [docs/methodology.md](docs/methodology.md)。

## scan 报告长这样

跑一下大致是这样(数字合成):

```
ai-eng-audit / your-repo / 2026-02-26 → 2026-05-27 (90d)

过去 90d,10 人提了 187 个 PR。142 个进了 `main`(75.9% scanned / 84.0% resolved)。
27 个开了又关没合。18 个还在 in flight,其中 4 个开了 30d+。Explicit revert <14d:2。
Org 级 AI 支出 $4,231.50(anthropic, openrouter);throughput 是 repo 级(scope mismatch)。

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

几个值得注意的对比:
  • window 内 PR 流量:+5 净变化(165 个 window 内创建,160 个 window 内关闭;与上方 'PRs opened' 口径不同——后者包括所有与 window 重叠的 PR)
  • top-5 / 10 个 author 贡献了 72.3% commits(50% 的人 → ~72% 的工作量)
  • merge 吞吐:142 个 merged / 90d ≈ 1.58 PR/天
  • AI 支出 $4,231.50 vs 142 个 merged PR(per-PR cost 不计算:scope_alignment = mismatch)

—
methodology v1.0。定义见 docs/methodology.md。
工作流信号,非个人评估。Tier 2 per-PR AI 归因后续版本接入。
```

## readiness checklist 长这样

跑 `addyosmani/agent-skills`(公开 OSS)真实结果:

```
ai-eng-audit / agent-skills / readiness checklist

CI / 测试:
  ✓ CI workflow  (.github/workflows/)
  ✗ tests 目录
  ✗ lint / formatter 配置

文档:
  ✓ README  (README.md)
  ✓ CONTRIBUTING 指南  (CONTRIBUTING.md)
  ✓ LICENSE  (LICENSE)

协作流程:
  ✗ CODEOWNERS
  ✗ PR template

配置 / 安全:
  ✓ .gitignore  (.gitignore)
  ✗ .env example

—
这是 presence checklist,不是评分。Agent 在共享上下文充足(CI、tests、ownership、docs)的 repo
里工作更可靠;缺项不阻塞 AI 使用,但会让 AI 产出更难 review、test、回滚。
```
