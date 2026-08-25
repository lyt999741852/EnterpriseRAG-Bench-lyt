# B3 Completeness 离线覆盖诊断（AB50 PageIndex ON）

日期：2026-08-25（Asia/Shanghai）

基线：`pageindex_ab50_semantic_consensus_20260820_r3_on`，综合分 59.34。分析范围为其已完成运行的两道 `completeness` 题。`expected_doc_ids` 仅在运行结束后用于离线归因，不参与线上检索、路由、候选或生成。

## 结论

两题均为 retrieval/citation gap，但失败层不相同，**禁止以一个“缺失分面补检索”开关同时处理**。

| Question ID | 目标文档数 | Raw | Post-rerank | Final | Submitted | 官方文档召回 | 完整度 | 判断 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `qst_0432` | 6 | 6 | 6 | 5 | 3 | 50% | 0% | 原始检索完整；问题在 final/submitted 证据覆盖缩减。 |
| `qst_0447` | 6 | 4 | 1 | 0 | 0 | 0% | 0% | raw 已不完整，rerank 又大幅丢弃，最终没有目标证据。 |

`qst_0432` 的答案正确地给出最高报告渠道（Jira），但官方理由指出缺少具体 ticket-type 细节；无额外文档。它是 selector/citation 覆盖问题，而不是需要扩大 raw 召回的问题。

`qst_0447` 要求 Hosted 与 Dedicated 的完整 hotfix 过程。官方理由显示答案错误地声称 Dedicated 过程和 rollout/rollback 证据缺失；本次有 1 个无效额外文档。它同时具有 raw、rerank 和最终证据层缺口，不能用 `qst_0432` 的 selector 策略验证。

## B3.P 门禁

只读 probe 必须拆分：

1. `qst_0432`：检查从 post-rerank 到 final/submitted 的 document 与 evidence-selection 决策；不得修改检索查询、候选预算或 rerank。
2. `qst_0447`：检查完整题干和现有分面查询是否已经覆盖 Hosted、Dedicated、审批、checklist、rollout/rollback、客户沟通；并单独记录 raw 到 post-rerank 的文档位次变化。

只有其中一条存在未被基线等价查询覆盖、且可隔离的变量，才允许提出对应的最小实现与固定 smoke。不得使用 benchmark 真实题型或目标文档来驱动线上逻辑。

原始审计 JSON 保留在忽略的 `outputs/pageindex_ab50_semantic_consensus_20260820_r3_on/completeness_coverage_audit.json`，不纳入提交。
