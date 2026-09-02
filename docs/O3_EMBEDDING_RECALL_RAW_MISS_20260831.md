# O3：raw-miss 子集的 BGE-small / Conan 原始召回对比

日期：2026-08-31
状态：已完成隔离诊断，尚未合入主流程

## 目的与边界

O0 将 F500 DPV4 结果中的 76 个 raw-miss 按是否存在 gold 文档进一步筛选，得到 46 道“有明确 gold 文档、但原始候选未命中”的有效 raw-miss。本实验只在这 46 道题上使用原始问题文本分别查询现有 BGE-small 和 Conan 索引，统计 gold 文档在 top-K 的覆盖情况。

本实验不调用 query rewrite、rerank、PageIndex、路由或生成模型，也不修改任一索引；因此结果只回答“换 embedding/索引是否有机会解决当前 raw-miss”，不等同于最终 RAG 分数。

## 实验配置

| 项目 | BGE-small | Conan |
|---|---|---|
| 向量维度 | 384 | 1792 |
| ES 索引 | `enterprise-rag-bge-small-v1` | `enterprise-rag-qwen3-emb-v3-conan448` |
| 索引文档数 | 928,534 | 3,030,317 |
| 查询向量 | 本地 `BAAI/bge-small-en-v1.5` | `live-embedding` API，返回 1792 维 |
| 查询文本 | 同一份原始题目 | 同一份原始题目 |
| 并发 | 8 | 8 |

## 结果（46 道有效 raw-miss）

指标是“题目中 gold 文档的平均覆盖率”；当前每题只有一个主要 gold 文档，因此也等价于题目命中率。

| 模型 | @30 | @120 | @240 | @1000 |
|---|---:|---:|---:|---:|
| BGE-small | 0.00% | 0.00% | 4.35% | 10.87% |
| Conan | 0.00% | 2.17% | 4.35% | 8.70% |
| Conan − BGE | +0.00pp | +2.17pp | +0.00pp | −2.17pp |

按题型看，semantic（35 题）在 @1000 为 BGE 11.43%、Conan 5.71%；basic（8 题）为 BGE 12.50%、Conan 25.00%。completeness（2 题）和 intra-document reasoning（1 题）两者均为 0%。

在 top-1000 内，BGE 命中 5 题，Conan 命中 4 题；两者互补命中，但没有形成整体增益。Conan 仅在少数 basic 题把 gold 文档提前到 @120，未改善 semantic 主体。

## 结论

1. **Conan 不是当前 raw-miss 的直接解法。** 在最主要的 semantic raw-miss 子集上，Conan 的 @1000 命中率反而低 5.72pp；没有理由立即用 Conan 替换当前 BGE-small 并重跑完整 F500。
2. **问题不只是向量维度。** 两个索引的文档规模和切块分布不同（约 92.9 万 vs 303.0 万），本实验同时包含模型、切块和索引覆盖差异；但即便在这个有利于 Conan 的更大索引上，也未见 raw-miss 的整体改善。
3. **优先级应转向索引/候选覆盖诊断。** 对 46 题逐题检查 gold 文档是否存在、gold chunk 的切块位置及 lexical 命中情况；若 gold 文档存在但向量长期排不到前列，应做通用的 dense+BM25 候选并集或扩大候选池，而不是继续做题目级改写。
4. **下一步建议。** 先做 O3.1：对这 46 题追加 `doc_id` 存在性、BM25 命中和 dense rank 三联表，区分“索引缺失”与“语义相似度排序失败”；只有发现 Conan 在独立同切块条件下有显著 raw recall 增益，才值得做小样本 RAG smoke。

复现实验脚本：`scripts/diag/compare_o3_embedding_recall.py`。
