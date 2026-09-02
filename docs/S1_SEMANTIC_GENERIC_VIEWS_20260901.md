# S1：通用 Semantic 查询视图离线回放

日期：2026-09-01  
状态：完成离线测试，未放行 RAG smoke

## 实验定义

本轮只使用问题文本，生成三个不含题目答案或文档实体的通用视图：

- `event`：事件/会议语境；
- `relation`：参与方、角色、动作和责任关系；
- `object_time`：对象、交付物、时间和截止条件。

每个视图分别运行 BGE-small dense 和正文 BM25 top-500。原始 dense/BM25 结果作为基线；另外计算所有视图的集合并集上限，以及“原始 RRF 前 120 + 尾部 append”候选池。qst_0247 只作为哨兵题，不参与规则设计。

## 结果

### Semantic 125 题

| 指标 | 原题 dense∪BM25 | 全视图集合并集 | 变化 |
|---|---:|---:|---:|
| Recall@30 | 56.8% | 60.0% | +3.2 pp |
| Recall@120 | 68.0% | 69.6% | +1.6 pp |
| Recall@240 | 75.2% | 76.0% | +0.8 pp |
| Recall@500 | 80.8% | 81.6% | +0.8 pp |

### 345 道非 Semantic 有效控制题

| 指标 | 原题 dense∪BM25 | 全视图集合并集 | 变化 |
|---|---:|---:|---:|
| Recall@30 | 92.75% | 93.91% | +1.16 pp |
| Recall@120 | 95.94% | 96.23% | +0.29 pp |
| Recall@240 | 97.10% | 97.10% | 0 pp |
| Recall@500 | 97.68% | 98.26% | +0.58 pp |

全视图并集是理想上限，不等价于主链的排序结果。每题平均耗时约 2.7–2.9 秒，约为单原题双路检索的数倍；如果没有明显召回收益，不适合直接全量启用。

### qst_0247 哨兵题

通用视图为：

- `event meeting call discussion sales call concrete pilot inputs deliverables`
- `participants roles responsibilities actions partner vendor isv planning due dates send`
- `objects deliverables timeline deadlines sales call concrete pilot inputs dates late december`

原题和三个视图的 dense/BM25 均未在 top-500 命中标准文档。该题仍是 raw-miss，说明仅把问题拆成通用词槽，无法跨越“问题中的 vendor/ISV”与“文档中的 Orbital Networks/Redwood co-sell sprint”之间的表达差异。

## 诊断结论

1. 通用视图没有引入答案泄漏，且对 Semantic 整体有小幅正向上限，但增益不足以证明可以进入主链。
2. qst_0247 的失败发生在 raw retrieval，不能靠 rerank、PageIndex 或生成提示词修复。
3. 低关键词重合 Semantic 的主要缺口不是视图数量，而是文档级证据聚合和标题/首段定位：事件主题在首 chunk，截止日期在后续 chunk，当前 chunk-level 检索无法合并。
4. “原始前 120 + 语义视图 append”必须以主链真实 RRF 前 120 为基准；集合并集指标只能作为召回上限，不能直接当作提升。

## 下一步

不进入 RAG smoke。下一阶段测试 S2 文档级聚合：将同一文档多个 chunk 的事件、角色、对象和时间命中合并，并增加首 chunk/header 优先分支；仍保留原题 dense/BM25 托底。只有 Semantic 125 获得跨题型稳定收益、控制题不回退后，才重新测试 top-500 append 和 20 题 RAG smoke。
