# S2.1：Document-profile 检索与 chunk expansion

日期：2026-09-01  
状态：完成只读诊断；不放行主链或 RAG smoke

## 实验目的

验证“先定位文档、再展开事实 chunks”是否能解决 Semantic 题中主题信息位于首段、具体事实位于后续 chunk 的错配问题。生产索引和答案生成均未修改；gold 文档仅用于离线统计。

## Shadow index 构建

- 来源：`o391_bge_meta_bm25_20260901`。
- 过滤：每个文档的 `chunk_index=0`。
- profile 表示：复制首 chunk 正文到 `profile_text`，保留 `title/file_path/section_context/lexical_context` 等 metadata；复用已有 BGE-small embedding，不重新编码。
- 目标：`o392_bge_doc_profile_20260901`，共 511,961 个 profile 文档。
- `_reindex`：无 failures、无 version conflicts；生产 alias 未切换。

这是一项“独立 profile 字段/索引”的结构验证，不等同于真正由整篇文档摘要重新生成的 document embedding。

## 检索与 expansion

每题并行执行：

1. profile dense top-100；
2. profile BM25（`profile_text`、`lexical_context`、`title`、`file_path`）top-100；
3. dense/BM25 文档级 RRF top-100，选择前 50 个文档；
4. 用 `terms doc_id` 回查 source chunks，统计 expansion 是否保留 profile 排名。

Expansion 统计已按 profile 文档顺序计算，避免 Elasticsearch 按 `chunk_index` 返回造成虚假的 top-k 排名。

## 结果

### 文档候选命中率

| 题组 | 方案 | Top-10 | Top-20 | Top-30 | Top-50 |
|---|---|---:|---:|---:|---:|
| Semantic 125 | profile dense | 11.2% | 16.0% | 17.6% | 24.0% |
| Semantic 125 | profile BM25 | 24.8% | 29.6% | 32.0% | 33.6% |
| Semantic 125 | profile RRF | 26.4% | 30.4% | 34.4% | 40.8% |
| Semantic 125 | RRF 后 expansion | 26.4% | 30.4% | 34.4% | 40.8% |
| 控制 345 | profile dense | 57.68% | 62.90% | 66.38% | 69.57% |
| 控制 345 | profile BM25 | 64.64% | 69.28% | 73.62% | 78.55% |
| 控制 345 | profile RRF | 71.88% | 78.26% | 80.00% | 83.48% |
| 控制 345 | RRF 后 expansion | 71.88% | 78.26% | 80.00% | 83.48% |

S2 的原始 chunk 按 `doc_id` 聚合在 Top-30 为 Semantic 47.2%、控制题 91.88%。因此当前 profile RRF 在同一 Top-30 口径下分别低 12.8 pp 和 11.88 pp，未达到“跨题型增益且控制题无回退”的门槛。

profile dense/BM25 的 top-100 联合曾触及 Semantic gold 文档 64/125、控制题 316/345；但只扩展前 50 个 profile 文档时，实际保留为 51/125 和 288/345。Expansion 本身不改变文档排序，无法挽救未进入 profile 候选的文档。

### qst_0247 哨兵题

`dsid_cc2f84330d014d03b8c49f8e92063b07` 在 profile dense、profile BM25、profile RRF top-100 均未命中，前 50 文档 expansion 也未命中。原因与 S1/S2 一致：问题使用 vendor/ISV/试点材料的泛化描述，而首 chunk 的实体和 GTM 主题表征仍不足以跨越表达鸿沟；后续 chunk 中的 12/22、12/23、12/29 事实只有在文档被定位后才可展开。

## 结论与决策

1. **chunk expansion 机制本身可安全实现**：回查 source chunks 不丢失已选文档，且统计已确认按 profile rank 保序。
2. **当前 profile 表示不合格**：它只是 chunk-0 的复制/复用，不是真正的文档级主题摘要；Semantic 和控制题均明显低于 S2 原始 chunk 聚合。
3. **不进入 RAG smoke、不合入主链**：没有证明生成阶段能得到更好的事实证据，继续扩大候选只会放大 profile 表示缺口。
4. **下一步方向**：保留原始 dense/BM25 作为托底；若继续 S2，应构建真正的文档 profile（标题、路径、首段及多个高信息 chunk 的压缩/摘要，或对文档内 chunk 分数做 max/sum-top-n 聚合），并用同一 470 题先做离线 Recall 对照。不得用 qst_0247 的实体或答案硬编码。

