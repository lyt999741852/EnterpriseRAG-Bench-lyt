# S4 全量 500 题：多路召回 + 文档级保留

启动日期：2026-09-03  
运行目录：`outputs/s4_full500_docaware_union_20260903/`（远端同名目录）

## 目的

在已冻结的 S3 全量基线上，验证近几轮小样本中可复用、且不依赖题目答案的两项改动能否改善全量结果：

1. 保留通用的原题、词法、语义、facet 四路 hybrid，并将每路及 RRF 候选扩大到 Top-500，避免语义题在单一路径中丢失。逐题 facet planner 的额外请求因单题耗时过高暂不纳入本轮全量。
2. 生成前采用文档级 admission：最终 rerank 证据优先，再从 pre-rerank Top-500 追加未覆盖文档；每文档最多 2 个 chunk、最多 10 个文档、最多 30 个 chunk，并把高排名证据交错放到上下文两端。

## 明确不纳入

- 不启用 PageIndex。
- 不做题型路由或 gold-aware 分支；`question_type` 只作为生成提示的题型上下文，不参与检索条件。
- 不采用尚未恢复的 rerank 服务批量优化实验（C1）；本轮固定使用 RRF 顺序作为 fail-open relevance order，明确记录 rerank bypass，不改写基线。

## 阶段与产物

1. `retrieval_report.json`：500 题固定四路 hybrid Top-500，记录 pre-rerank Top-500 与候选覆盖。
2. `answers.jsonl` / `generation_report.json`：DPV4 生成、文档级 admission、edge-packed 上下文及逐题覆盖。
3. `official_score/results.json`：官方评分模块，`--no-correction`，与 S3 同口径。

全部文件写入独立目录，完成后与冻结基线的正确性、完整性、综合分、文档召回及十类题型逐项比较。
