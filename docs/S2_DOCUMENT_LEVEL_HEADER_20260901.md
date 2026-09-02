# S2：文档级 chunk 聚合、首段/header 优先与文档候选定位

日期：2026-09-01  
状态：完成离线诊断；当前 header 加权方案不放行 RAG smoke

## 实验定义

固定 BGE-small 生产索引、原题向量和 470 道有效题（Semantic 125、控制 345）。每题只使用问题文本查询：

- 原始 dense top-500；
- 原始正文 BM25 top-500；
- 首 chunk 优先的 BM25（`chunk_index=0` 加权）；
- 首 chunk 过滤的 dense；
- 按 `doc_id` 聚合多 chunk 的 rank evidence。

gold 文档 ID 只在检索完成后用于统计，不参与查询构造。

## 结果

### 文档候选命中率

| 题组 | 方案 | Top-10 | Top-20 | Top-30 |
|---|---|---:|---:|---:|
| Semantic 125 | 原始 dense/BM25 文档聚合 | 31.2% | 41.6% | 47.2% |
| Semantic 125 | header lane 低权重聚合 | 28.8% | 32.8% | 36.0% |
| Semantic 125 | header lane 高权重聚合 | 27.2% | 32.8% | 36.0% |
| 控制 345 | 原始 dense/BM25 文档聚合 | 83.77% | 89.57% | 91.88% |
| 控制 345 | header lane 低权重聚合 | 80.0% | 83.77% | 86.38% |
| 控制 345 | header lane 高权重聚合 | 77.68% | 83.19% | 85.22% |

header lane 虽然使 Semantic gold 文档被某个 header 查询触及的题数从 101 增加到 102，且控制题从 337 增加到 339，但它没有把这些文档排进前 10/20/30，反而因泛化标题/首段竞争导致候选排序回退。

### qst_0247 哨兵题

该题在原始 dense/BM25 top-500 中没有 gold 文档，在首 chunk BM25 和首 chunk dense top-500 中也没有 gold 文档。文档级聚合无法恢复一个没有进入任一候选源的文档。

标准文档的有效信息分布在：

- chunk 0：`Orbital Networks`、GTM/co-sell 会议主题、参与人和 pilot 背景；
- 后续 chunk：具体的 12/22、12/23、12/29 行动项。

当前 chunk-0 向量和正文本身没有把该文档召回，说明简单 header boost 不是通用解法。

## 诊断结论

1. **文档级聚合值得保留为方向**：同一文档多个 chunk 分别命中不同条件时，合并 doc-level evidence 是合理的通用机制。
2. **当前 header 加权方案否决**：直接提升 `chunk_index=0` 会放大泛化标题、摘要和噪声，Semantic 与控制题的文档排序都下降。
3. **qst_0247 的主问题仍是查询表示/文档表示不匹配**，不是 rerank 或生成阶段；gold 文档在所有 header lane top-500 之外，候选保留也无法挽救。
4. 需要把“文档定位表示”和“事实 chunk 表示”分开：文档定位应使用可检索的标题/摘要/主题表示，命中文档后再展开事实 chunks。不能把一个原始 chunk-0 当作完整文档摘要。

## 下一步

不进入 RAG smoke，不把当前 header 权重合入主链。下一步做 S2.1：

- 从现有文档首段/标题/摘要构建独立的 document-profile shadow index；
- 使用文档级 dense/BM25 排名，再回查该文档全部 chunks；
- 比较 `max chunk score`、`sum top-n chunk evidence`、`document-profile + chunk expansion` 三种方案；
- 仍保留原始 dense/BM25 作为托底，候选前段不丢失。

只有 S2.1 在 Semantic 125 上获得跨题型增益、且控制题无回退后，才重新尝试 top-500 append 和 20 题 RAG smoke。
