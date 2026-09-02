# O3.8：dense/BM25 top-240/500 与 wide-rerank smoke（2026-09-01）

## 实验范围

本轮先在当前 BGE-small 生产索引上做只读 top-k 扫描，再尝试 20 题 RAG smoke。扫描使用原题 embedding 和原题 BM25，分别取 30/120/240/500；并集指标按 `dense[:k] ∪ BM25[:k]` 计算。RAG smoke 使用独立配置：`retrieval.candidate_k=500`、`reranker.candidate_k=240`，其余沿用 DPV4/BGE-small 基线。生产索引没有写入。

## top-k 扫描结果

### O0 有效 raw-miss（46 题）

| 召回方式 | @30 | @120 | @240 | @500 |
|---|---:|---:|---:|---:|
| dense | 0.00% | 0.00% | 4.35%（2/46） | 8.70%（4/46） |
| BM25 | 0.00% | 0.00% | 13.04%（6/46） | 26.09%（12/46） |
| dense ∪ BM25 | 0.00% | 0.00% | **17.39%（8/46）** | **32.61%（15/46）** |

目前生产 pre-rerank 的有效窗口相当于 top-120，因此原题两路在这 46 题上均为 0 命中。扩大到 240 可带回 8 题，扩大到 500 可带回 15 题；命中的目标大多位于 120 之后，说明这不是简单的 selector/admission 问题。

### 470 道有效题控制

| 召回方式 | @30 | @120 | @240 | @500 |
|---|---:|---:|---:|---:|
| dense | 53.19% | 61.70% | 66.17% | 71.49% |
| BM25 | 80.64% | 85.96% | 88.09% | 90.21% |
| dense ∪ BM25 | **82.98%** | **88.51%** | **91.28%** | **93.19%** |

Semantic 125 题的并集命中为 @120 68.00%、@240 75.20%、@500 80.80%；Basic 题为 93.71%→95.43%→96.00%。扩大窗口没有破坏原有前段集合，但会增加候选数量和下游成本。

## RAG smoke 结果

20 题 wide-rerank smoke 已启动并完成索引读取、原题/改写/意图检索，但在 rerank 输入 240 条时超时退出：

- 已写出 2/20 题的答案和 route trace；
- 错误为 rerank 服务 `TimeoutError`，不是 ES、embedding 或索引错误；
- 没有生成完整评分文件，因此本轮不能报告 correctness、combined 或有效的生成收益。

这次失败本身给出成本边界：当前 rerank 服务和并发设置不能稳定承受 240 条输入；直接把 reranker candidate_k 从 120 提到 240 不适合作为主链方案。

## 判断

1. **通过 pre-rerank 召回方向**：top-240/500 的原题 dense+BM25 集合确实恢复了一部分 raw-miss，尤其 Semantic；应继续保留原题两路。
2. **否决 wide-rerank=240**：服务超时且无最终分数，不进入主链，不申请 AB50。
3. **候选实现调整**：下一版保持 rerank 输入 120，先把 BM25/dense 各取 500；从两路尾部做严格 append-only reserve，确保前 120 不被改写，同时限制每文档 chunk 数。
4. **下一步 smoke**：在同一 20 题上测试 `retrieval candidate_k=500 + reranker candidate_k=120 + append-only reserve`，检查 raw/pre-rerank gold 进入率和控制题；只有该版本稳定完成，才比较 no-correction 评分。
