# R10 题型作用域、软配额与词法锚点 smoke

日期：2026-08-27

## 目标

R10 一次验证三项系统级改造：

1. semantic rescue / facet quota 增加题型作用域，避免 basic 控制题被注入额外检索视图。
2. 将全局硬总量截断改为“每文档最多 2 个 chunk、每个文档至少保留 1 个”的软配额，不再按固定顺序删除多跳证据。
3. 对 semantic、unknown、project_related、completeness 生成题干派生的实体/数字/版本词法对查询，低权重加入 keyword 候选池。

## 运行与资源

使用 AB50 A4/B4 基线中的 12 题：5 个 raw-miss、3 个 project、2 个 completeness 题和 1 个 semantic 控制题 `qst_0272`，另含 `qst_0447` 多分面题。固定 question-only 输入，不使用目标文档锁定。

第一次并发 2 和第二次单并发运行因 reranker 连接重置失败；第三次显式透传 `LARK_API_KEY` 与 `EMBEDDING_API_KEY`、单并发完成 12/12。远端临时补丁随后已回滚并通过语法检查。

## 官方 no-correction 结果

| 指标 | A4/B4 12 题子集 | R10 | 变化 |
|---|---:|---:|---:|
| Correctness | 25.00% | 25.00% | +0.00pp |
| Completeness | 27.02% | 18.30% | -8.72pp |
| Combined | — | 15.74 | — |
| Document recall | 21.07% | 10.65% | -10.42pp |
| Invalid extra docs | 0.58 | 0.42 | -0.16 |

R10 结果不是可放行的提升：额外文档略降，但证据召回和完整性同步下降。

## 关键诊断

- 12 题中 6 题的 LLM inferred route type 与离线基准类型不同：`qst_0184`、`qst_0251`、`qst_0298`（semantic→constrained），`qst_0272`（semantic→basic），`qst_0356`（project_related→constrained），`qst_0447`（completeness→intra_document_reasoning）。因此“按 inferred type 开关 rescue/quota”不是稳定的题型隔离机制。
- `qst_0272` 本轮被推断为 basic，未出现 R9 中的控制题空文档回退；但同一题型推断存在漂移，不能作为可靠门禁。
- 词法变体每题产生 10–16 个实体对查询，`qst_0231` 等题能获得额外 rewrite/answer-intent/facet 候选，但这些候选没有稳定进入最终选中文档；raw-miss 仍未形成可验证的召回增益。
- 软配额 trace 中候选通常为 30→30（`qst_0350` 个别为 30→29），说明 R9 的主要回退并非单纯总量上限，而是后续 PageIndex/selector/generation 的文档保留与路由决策。
- `qst_0350` 本轮 correctness/completeness 与基线基本保持，说明“每文档保留一条”比固定总量截断安全，但没有解决多跳题的最终证据选择。

## 结论

R10 **不通过、不合流、不运行 F500**。三项同时接入没有带来检索改善，且词法查询数量显著增加了 reranker 压力；此前两次连接重置也说明该方向当前资源成本偏高。

## 后续 1/2/3 计划调整

1. 路由层先改为稳定的“路由置信度/模式”契约：当 inferred type 不确定或与 route plan 不一致时，保持基线视图，不启用 rescue/quota；不能只依赖单次 LLM 类型字符串。
2. 保留软配额的“每文档一条”原则，但把文档保留放到 PageIndex/selector 交界处，按分面覆盖和多跳文档集合保护证据；不再增加固定数量的全局检索结果。
3. raw-miss 词法方向先退回离线索引诊断：统计实体对命中后的 rank、进入 rerank、进入 PageIndex、进入 generation 的逐层漏斗；只有确认某一锚点在真实链路中稳定穿透，才做 3–5 题小 smoke。
