# B2 Project 离线覆盖诊断（AB50 PageIndex ON）

日期：2026-08-25（Asia/Shanghai）

基线：`pageindex_ab50_semantic_consensus_20260820_r3_on`，综合分 59.34。分析范围为该已完成运行的 4 道 `project_related` 题。`expected_doc_ids` 仅在运行结束后用于离线归因，不参与任何线上查询、路由、候选或生成。

## 分桶结果

| 类别 | 题数 | Question ID |
|---|---:|---|
| Generation coverage gap | 1 | `qst_0341` |
| Retrieval/citation gap | 3 | `qst_0350`, `qst_0356`, `qst_0362` |

所有题至少命中一个目标文档，因此只用“是否命中任一目标文档”的旧分层会误把多文档覆盖不足归为生成问题。本次审计改为逐目标文档核验 raw、pre-rerank、post-rerank、final context 和 submitted 五个阶段。

## 逐题证据

| Question ID | 目标文档数 | Raw 命中 | Post-rerank 命中 | Final/Submitted 命中 | 官方文档召回 | 完整度 | 判断 |
|---|---:|---:|---:|---:|---:|---:|---|
| `qst_0341` | 2 | 2 | 2 | 2 / 2 | 100% | 90% | 纯生成覆盖缺口；不属于 B2 检索改动目标。 |
| `qst_0350` | 3 | 3 | 1 | 2 / 2 | 66.67% | 88.89% | 原始召回完整，但 rerank 后丢失两个目标，最终只恢复其中一个。 |
| `qst_0356` | 4 | 2 | 2 | 2 / 1 | 25% | 50% | 原始召回缺失两个目标，且 final 到 submitted 又丢失一个；另有 1 个无效额外文档。 |
| `qst_0362` | 9 | 3 | 2 | 1 / 1 | 11.11% | 30.77% | 多文档原始召回不足，随后 rerank/selector 继续缩减覆盖。 |

## B2 门禁结论

不直接接入统一的“项目名/组件名词法锚点”改动，也不改变 RRF 权重、候选预算或 PageIndex。证据显示失败层不同：

- `qst_0350` 需要单独验证多文档候选在 rerank 后的保留策略；词法锚点不能证明会修复该后段丢弃。
- `qst_0356` 和 `qst_0362` 的主要问题是原始多文档召回不足，且仍有 selector/citation 覆盖问题。
- `qst_0341` 已有完整证据，应保留给后续生成覆盖任务，而不是混入 B2。

下一步仅做 B2.P：对 `qst_0356`、`qst_0362` 进行问题文本约束、只读的 Project entity/组件/路径 token 覆盖 probe，并对 `qst_0350` 单独记录 rerank 前后文档位次。只有 probe 对 raw 覆盖或 rerank 保留给出可重复改善且无额外文档恶化，才提出最小实现和固定 smoke 配置。

原始离线审计 JSON 位于忽略的 `outputs/pageindex_ab50_semantic_consensus_20260820_r3_on/project_coverage_audit.json`，不纳入提交。
