# O4.P3：semantic/constrained selector 稳定性 smoke（2026-08-31）

## 实验设置

在 O4.P2（soft pool +2、selector 候选预算 30）基础上，启用 selector 稳定性兜底：

- `evidence_selection_fail_closed=false`；
- `evidence_selection_fallback_chunks=4`；
- `evidence_selection_anchor_chunks=2`。

其它条件保持 BGE-small 索引、BM25+dense+RRF、rerank、PageIndex、DPV4、20 题题集和官方 `no-correction` 不变。额外文档数量按打榜规则不设硬限制，仅记录观察。

## 官方评分

| 指标 | O4.P 控制 | O4.P2 | O4.P3 | P3 相对控制 |
|---|---:|---:|---:|---:|
| correctness | 60.00% | 80.00% | **90.00%** | +30.00pp |
| completeness | 63.98% | 77.07% | **79.29%** | +15.31pp |
| combined | 56.48 | 71.48 | **79.29** | +22.81 |
| document recall | 59.58% | 73.33% | **74.17%** | +14.59pp |
| invalid extra docs | 0.15 | 0.35 | 0.20 | +0.05（可接受） |

三组均为 20/20 完成、0 skipped、0 corrected。P3 相比 O4.P2，correctness +10pp、combined +7.81，额外文档反而下降 0.15。

## 重点题型

- `semantic`：相对控制 correctness 66.67% → 66.67%，但相对 O4.P2 的 33.33% 恢复；`qst_0176` 从 selector 无文档/拒答恢复为目标文档答案，召回回到 100%。
- `constrained`：相对 O4.P2 correctness 50% → **100%**，completeness 89.28% → **100%**；额外文档可接受，不再作为门槛。
- `intra_document_reasoning`：correctness/completeness/recall 均为 100%。
- `project_related`：correctness 100%，completeness 80.83%，召回 72.22%。
- `basic`：correctness 保持 100%，但个别题 completeness/recall 受 DPV4 运行漂移影响，需在更大样本复核。

## 稳定性证据

本轮 answers 中 `document_ids` 为空的题数为 **0/20**（O4.P 为 3/20，O4.P2 为 2/20）。这说明 fallback/anchor 有效抑制了 selector fail-closed 导致的空证据路径；它不改变召回来源，也不锁定 gold 文档。

## 结论与下一步

O4.P3 是当前最值得进入更大样本的配置：它保留软融合带来的文档覆盖，同时解决了 semantic/constrained 的 selector 空集回退。由于 DPV4 生成存在服务端漂移，20 题结果仍不能直接等价为 F500 提升。

下一步进入 50 题 no-correction 验证，固定 O4.P3 参数，重点统计 semantic、constrained、intra_document_reasoning 与 basic 控制题，并与冻结 BGE+DPV4 基线对齐 correctness、completeness、combined、recall 和空文档答案率。

产物目录：`outputs/pageindex_o4p3_soft_pool_smoke20_20260831/`。
