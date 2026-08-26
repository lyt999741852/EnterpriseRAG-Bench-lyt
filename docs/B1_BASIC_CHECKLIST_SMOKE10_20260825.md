# B1 Basic 事实清单 Smoke10 结论

日期：2026-08-25（Asia/Shanghai）

## 结论

**未通过，停止 B1.1，不运行 AB50 全量评测。**

实验仅为 LLM 推断为 `basic` 的生成路径增加受证据约束的事实清单提示。BM25、dense、RRF、reranker、PageIndex、chunk、候选预算和题目路由均未修改。固定的 10 题配置使用独立 output 与 PageIndex cache，单并发运行并完成官方 `--no-correction` 评分。

## 运行完整性

| 检查 | 结果 |
|---|---:|
| 固定题目数 | 10 |
| `answers.jsonl` | 10 |
| `route_trace.jsonl` | 10 |
| 官方评分完成题数 | 10 |
| pipeline simple recall | 87.5 |
| pipeline simple invalid docs | 0.1 |

## Basic 目标对照

| Question ID | 基线完整度 | Smoke 完整度 | 文档召回 | 无效额外文档 | 结论 |
|---|---:|---:|---:|---:|---|
| `qst_0013` | 80 | 80 | 100 | 0 | 未改善 |
| `qst_0079` | 75 | 75 | 100 | 0 | 未改善 |
| `qst_0119` | 50 | 50 | 100 | 0 | 未改善 |

6 个 Basic 题中，3 个完全成功、3 个仍为 generation coverage gap；Basic 平均完整度为 84.17%，平均文档召回 100%，平均无效额外文档为 0。两个 InfoNotFound 对照题均正确、完整度 100%，且未提交额外文档。

一个非 Basic Semantic 对照题 `qst_0184` 的本次结果为正确性 0、完整度 0、文档召回 0、无效额外文档 1。该规则不会在非 Basic 路由生效，不能据此归因；但它进一步说明这组 smoke 不具备推进全量评测的安全性。

## 后续处置

- 已从本地工作树删除 B1 的路由规则，并提供远端精确回滚脚本；远端测试规则会立即回滚。
- 保留生成器、配置、启动和回滚脚本，以便复核此失败实验；不将该规则接入后续任务。
- 下一个候选任务回到 B2 的离线 Project 分桶与只读证据诊断；需先建立其基线后再提出实现变更。

原始答案、trace、评分及 Basic 分桶 JSON 保留在忽略的 `outputs/b1_basic_checklist_smoke10_20260825/`，不纳入提交。
