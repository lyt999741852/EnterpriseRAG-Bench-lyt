# O3.9：Metadata 来源审计、BGE shadow index 与 top-500 对照

日期：2026-09-01  
状态：O3.9.1–O3.9.3 完成；O3.9.4 smoke 未通过服务稳定性门槛；未申请 AB50

## 结论先行

本轮证明 BGE 生产索引的向量和正文复制没有损坏，缺口主要不是索引丢文档，而是有效信息没有进入当前 chunk 的可检索文本。通过 manifest 回填 metadata 不需要重算 embedding，但简单把 metadata 混入单一路 BM25 会改变控制题排序并造成回退。最安全的方向是保留原 text BM25/dense 前 120，把 metadata 作为独立的低权重 recall lane 或尾部 reserve；本轮未将其合入生产主链。

## O3.9.1 来源与覆盖审计

- corpus 文件：511,961；唯一 doc_id：511,957；4 个重复 doc_id；无缺失路径。
- BGE 与 Conan manifest：各 511,961 行、511,957 个唯一 doc_id、4 个重复、0 个缺失路径；gold 文档均可映射。
- BGE ES：928,534 chunks；Conan ES：3,030,317 chunks。
- 生产 BGE/Conan mapping 中 `title`、`file_path`、`section_context`、`lexical_context` 均不存在可用值；全库与 61 个 raw-miss gold 文档的字段存在率均为 0%。

因此，两个数据集都存在 metadata 不可检索的问题，但没有发现 doc_id/路径覆盖导致的系统性丢失；若要改变 chunk 正文或切块边界仍需重新 embedding，单纯补 metadata 不需要重建向量。

## O3.9.2 版本化 shadow index

建立 `o391_bge_meta_bm25_20260901`，通过 ES `_reindex` 复制 BGE-small 的原向量和正文，再从 manifest 回填：

- `title`：文件名中 `__` 后的标题 slug；
- `file_path`：规范化源路径；
- `section_context`：父目录；
- `lexical_context`：标题、父目录和路径的可审计拼接。

结果：928,534/928,534 文档，bulk failure=0；三个字段覆盖率均 100%；生产 index/alias 未修改。shadow text-only 基线与生产扫描一致，说明复制过程未改变 dense/BM25 结果。

## O3.9.3 top-500 对照

固定 470 个有效题、46 个 O0 raw-miss，原题 embedding，dense/BM25 各取 top-500。

| 方案 | raw-miss union @120 | @240 | @500 | 有效题 union @500 |
|---|---:|---:|---:|---:|
| 生产/ shadow text-only | 2.17% | 17.39% | 32.61% (15/46) | 93.19% |
| metadata `bool_should` 单路 BM25 | 8.70% | 19.57% | 34.78% (16/46) | 88.51% |
| text BM25 + metadata append union | 2.17% | 17.39% | 32.61% (15/46) | 92.98% |

`bool_should` 对 raw-miss 只有 +1/46 的增益，却使有效控制题 @500 union 下降 4.68 pp；原因是 metadata slug/路径词的统计分布重排了 BM25，而不是恢复正文中缺失的证据。保留原 text 顺序再 append metadata 候选没有可测增益，说明当前回填 metadata 的信息量不足。

## O3.9.4 20 题 RAG smoke

已实现临时 append-only 逻辑：dense/BM25 candidate_k=500，RRF/rerank 输入固定 120，raw hybrid tail 在 rerank 后最多追加 8 个候选；每文档 cap 沿用现有 admission 约束。两次以并发 1 重试均在首次 rerank 请求出现 `broken pipe/connection reset`，没有产生完整 answers/route trace，不能评分，也不能把失败归因于候选逻辑。临时 patch 已回滚，生产源码恢复。

## 放行判断与后续

1. 不放行 metadata 单路重排，也不申请 AB50。
2. 保留 shadow index 作为可复现实验资产；生产 alias 不切换。
3. 下一次 smoke 先做 rerank 服务 preflight/小 payload 健康检查，再运行 append-only reserve；若服务稳定，检查 rerank 输入恒为 120、前 120 不变、raw tail 只在后段进入 PageIndex。
4. metadata 继续作为独立低权重 lane，优先补充真实文档标题/章节/表头，而不是把粗粒度路径 slug 直接混入 BM25 主分数。
