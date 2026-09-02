# O4：文档/分面软融合固定轨迹回放（2026-08-31）

## 结论

O4 证明候选池存在明显的“文档覆盖不足”空间：在既有最终候选上只追加 rerank 阶段中来自未覆盖文档的代表 chunk，不删除原候选、不使用 gold 文档、不调用 LLM/ES/reranker/PageIndex，即可把 470 道有效题的文档召回从 **73.62%** 提升到：

| 方案 | 文档召回 | 相对基线 | 恢复题数 | 平均追加文档数 |
|---|---:|---:|---:|---:|
| baseline | 73.62% | — | — | — |
| soft pool +1 | 78.30% | +4.68pp | 22 | 0.96 |
| soft pool +2 | **80.00%** | **+6.38pp** | 30 | 1.92 |
| soft pool +3 | 80.64% | +7.02pp | 33 | 2.88 |

`+2` 是当前最合适的下一步候选：相较 `+1` 多恢复 8 道题，相较 `+3` 仅少恢复 3 道题，却少引入约 0.96 个文档/题，噪声和生成上下文膨胀更可控。

## 方法

- 输入：500 题 DPV4+BGE-small 的固定 `route_trace.jsonl`；其中 470 题有有效目标文档，`high_level/info_not_found` 不参与有效召回率。
- baseline：`retrieval_stages.final_before_generation.chunk_ids`。
- 候选来源：同一固定轨迹中的 `retrieval_stages.rerank.after.chunk_ids`。
- 软融合：按 rerank 顺序扫描，仅从 baseline 未出现的文档追加代表 chunk；每个新增文档最多 1 个 chunk，追加上限分别为 1/2/3。
- 隔离条件：不改写问题、不锁定 gold、不做 strict drop、不重新调用模型或检索服务，因此结果只衡量候选保留对文档覆盖的潜在收益。

## 分题型结果

| 题型 | 题数 | baseline | +1 | +2 | +3 |
|---|---:|---:|---:|---:|---:|
| basic | 175 | 79.43% | 85.14% | 86.86% | 87.43% |
| completeness | 20 | 80.00% | 85.00% | 85.00% | 85.00% |
| conflicting_info | 20 | 95.00% | 95.00% | 95.00% | 95.00% |
| constrained | 30 | 90.00% | 93.33% | 96.67% | 96.67% |
| intra_document_reasoning | 40 | 80.00% | 90.00% | 90.00% | 92.50% |
| miscellaneous | 20 | 95.00% | 100.00% | 100.00% | 100.00% |
| project_related | 40 | 97.50% | 100.00% | 100.00% | 100.00% |
| semantic | 125 | 44.00% | 47.20% | **50.40%** | 51.20% |

收益主要来自 semantic（+6.40pp，+2）和 intra-document reasoning（+10.00pp，+2）；completeness 提升 5pp，project-related 仅有小幅提升。conflicting_info 没有召回回退，说明“只增不删”的策略满足控制题约束。

## 边界与下一步

这是固定轨迹上的**文档召回**回放，不等价于最终 correctness、completeness 或 combined 分数提升。额外文档可能增加生成噪声、无效引用或 selector 压力，因此不能直接替换生产配置。

下一步做 O4.P：使用 `soft_pool +2` 在 10–20 题小样本上重新执行 DPV4 生成与官方 `no-correction` 评分，同时记录 correctness、completeness、combined、invalid extra documents、selector 清空率，并保留 basic/conflicting_info 作为控制题。若控制题无回退且 semantic/intra_document_reasoning 有净收益，再进入 50 题验证。

原始逐题结果由 `replay_o4_document_pool.py` 生成，便于复核和后续按题回放。
