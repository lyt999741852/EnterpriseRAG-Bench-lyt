# F500 BGE + DPV4 官方评分记录（2026-08-31）

## 状态

- 生成：已完成 500/500 题。
- 官方评分：`no-correction` 已完成，`completed_questions=500`、`skipped_rows=0`。
- 远程运行目录：`/opt/enterprise-rag-bench/app/outputs/pageindex_full500_bge_dpv4_20260831`
- 结果文件：`results.json`

## 固定条件

- 数据集/索引：当前 EnterpriseRAG 全量语料，既有 `enterprise-rag-bge-small-v1`（BGE-small，384 维）索引。
- 检索：hybrid（BM25 + dense，RRF），rerank，PageIndex 开启；未启用 parent expansion。
- 生成模型：DeepSeek-V4 Flash（`deepseek-v4-flash`），temperature 0，关闭 thinking。
- 评分：官方 `metrics_based_eval --no-correction`，评分调用 DPV4；未运行 correction。

## 全量结果

| 指标 | 本轮 |
|---|---:|
| correctness | **62.80%**（314/500） |
| completeness | **64.25%** |
| combined | **57.01** |
| document recall | **60.29%** |
| 平均无效额外文档 | **0.23** |

与冻结的 BGE + PageIndex 500 题 `no-correction` 基线（correctness 60.60%、completeness 62.57%、combined 55.18、recall 61.12%、无效额外文档 0.18）相比：

- correctness：+2.20 个百分点；
- completeness：+1.68 个百分点；
- combined：+1.83；
- recall：-0.83 个百分点；
- 无效额外文档：+0.05。

这说明 DPV4 替换后，全量答案判定/完整性有净提升，但检索召回没有同步提升，且轻微增加了额外文档污染；不能把提升归因于 embedding 或索引变化，因为本轮未更换 BGE-small 索引。

## 按题型结果

| 题型 | 数量 | correctness | completeness | combined | recall |
|---|---:|---:|---:|---:|---:|
| basic | 175 | 76.57% | 74.41% | 72.02 | 77.14% |
| semantic | 125 | 40.80% | 44.37% | 36.42 | 40.00% |
| intra_document_reasoning | 40 | 57.50% | 68.63% | 55.83 | 77.50% |
| project_related | 40 | 57.50% | 51.04% | 39.17 | 36.85% |
| constrained | 30 | 66.67% | 77.30% | 59.29 | 73.33% |
| conflicting_info | 20 | 55.00% | 60.43% | 44.94 | 40.00% |
| completeness | 20 | 45.00% | 45.08% | 33.06 | 23.03% |
| miscellaneous | 20 | 90.00% | 88.75% | 88.75 | 90.00% |
| high_level | 10 | 50.00% | 56.67% | 43.33 | 0.00% |
| info_not_found | 20 | 100.00% | 100.00% | 100.00 | 0.00% |

## 后续解释

本轮首先作为“当前数据集 + DPV4”全量插入任务的基准结果保存，不合并任何检索变量。后续优化仍应优先针对 semantic、completeness 和 project_related 的 raw-miss/候选覆盖问题；DPV4 的生成层收益与检索层收益应分开验证。
