# O2：低置信度 Shadow 候选固定 Replay（2026-08-31）

## 实验范围

- **输入**：F500-DPV4 已完成的 `route_trace.jsonl`，固定原始 keyword/dense、rewritten/intent dense 视图。
- **执行方式**：离线重算 RRF，不调用 embedding、ES、reranker、PageIndex 或 LLM；因此不会受重跑非确定性影响。
- **低置信度触发**：原始 keyword 与 dense 前 8 个文档无交集。
- **有效分母**：470 题；`high_level` 和 `info_not_found` 的 30 题无 `expected_doc_ids`，不纳入文档召回分母。

## 触发情况

共 **228/500** 题触发低置信度条件，其中 Semantic **97/125**、Completeness 7/20、Project-related 3/40；说明该条件较宽，不能直接等价为 raw-miss。

## 候选重排结果

| 方案 | Recall@30 | Recall@120 | Recall@240 | Recall@1000 |
|---|---:|---:|---:|---:|
| 原始 keyword+dense RRF | 79.79% | 86.81% | 88.51% | 88.51% |
| 低置信度后加入 shadow 并重新 RRF | **76.17%** | 86.81% | — | — |
| 低置信度后 append shadow（不重排原始候选） | — | — | 88.51% | **88.72%** |

按题型，Semantic 的 append-only Recall@1000 为 68.8%，较原始 68.0% 仅提升 0.8 个百分点；全量有效题仅提升 0.21 个百分点。@30 重新 RRF 反而造成 21 题丢失、仅恢复 4 题；@120 仅恢复 1 题、丢失 1 题。

## O2 判断

本轮 **不放行通用 shadow-RRF，不运行 O2 生成 smoke**：

1. 低置信度 shadow 重排在 @30 直接降低整体召回 3.62 个百分点，Basic、Conflicting、Miscellaneous 也出现下降。
2. append-only 不破坏原始 @120 候选，但只在 @1000 尾部带来极小增益，尚不足以证明对最终 RAG 有价值。
3. 该 replay 使用的是 F500 中已有 rewrite/intent 视图，不能证明全新 shadow query 一定无效；但可以排除“低置信度触发后直接低权重 RRF 合流”这一实现。

## 后续动作

- 保持原始 BM25+dense 为唯一主候选顺序，不接入 shadow-RRF。
- 若继续 O2，只允许做严格 append-only、低置信度且有候选空间预算的尾部补充，并先用固定候选 replay 验证；不得直接进入 PageIndex/生成链。
- 更高优先级转入 O3：在同一 raw-miss 子集上做替代 embedding 的 Recall@30/120/240/1000 隔离测试。当前证据更支持“表征/索引相关性不足”，而不是 query view 融合不足。
