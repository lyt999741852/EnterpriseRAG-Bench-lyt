# O3.2：gold 文档覆盖链路审计

日期：2026-08-31

## 审计范围

针对 O0 的 46 道有效 raw-miss，展开 61 个 gold `doc_id`，只读核对：

- `corpus/all_documents` 是否有对应 TXT；
- BGE-small 与 Conan 的 `manifest.sqlite3` 是否有对应记录及状态；
- O3.1 中两个 ES 索引是否实际包含对应 `doc_id`；
- F500 配置是否指向上述 corpus、manifest 和索引。

未调用生成模型、embedding、rerank 或修改索引。

## 结果

| 环节 | BGE-small | Conan |
|---|---:|---:|
| gold 文档数 | 61 | 61 |
| corpus TXT 存在 | 61/61 | 61/61 |
| manifest 记录存在 | 61/61 | 61/61 |
| manifest 状态为 `chunked` | 61/61 | 61/61 |
| ES 中实际存在 | 36/61 | 39/61 |
| ES 缺失 | 25/61 | 22/61 |

两套 ES 索引共有 10 个 gold 文档同时缺失；BGE 独有缺失 15 个，Conan 独有缺失 12 个。也就是说，缺失集合并不由某个题型或某个 embedding 模型完全决定，而是两个索引快照/入库过程各自存在覆盖差异。

### 配置核对

F500 配置 `configs/eval_pageindex_full500_bge_dpv4_20260831.yaml` 明确使用：

- corpus：`corpus/all_documents`；
- BGE 索引：`enterprise-rag-bge-small-v1`；
- PageIndex manifest：`.index_cache/full_es_bge_small/manifest.sqlite3`；
- `read_existing_index: true`，`overwrite_index: false`。

这意味着本次 F500 直接读取既有 ES 索引，不会因配置运行自动补齐缺失文档。

## 关键解释

### 1. 原始语料不是缺失源

61 个 gold 文档全部能在 `corpus/all_documents` 找到，且两套 manifest 都记录为 `chunked`。因此 raw-miss 的 `index_missing` 不是官方答案或 corpus 文件不存在。

### 2. manifest 不能证明 ES 已入库

BGE manifest 的 metadata 标注为 `pageindex_read_only_path_mapping`，且这些 gold 记录的 `chunk_count` 为 0；它主要用于 PageIndex 路径回读，不是可靠的 BGE ES 入库清单。Conan manifest 有实际 chunk 计数，但仍有 22 个 gold 文档在 Conan ES 中不可见，说明 manifest 与 ES 也不是同一层的完成证明。

### 3. 当前主要阻断点是索引快照/入库覆盖

F500 的 `read_existing_index=true` 与两个 ES 索引的缺失集合，足以解释 O3/O3.1 中大量 raw-miss。此时继续调 embedding、query rewrite 或 rerank，无法修复 `index_missing`；应先确认索引构建是否中断、是否使用了不同 corpus snapshot、是否存在旧索引复用或分片入库遗漏。

## 后续建议（O3.3）

1. 以 61 个 gold 文档为白名单，读取两个索引的 `_count`/`terms` 结果和构建日志，确认每个缺失 doc 是否从未入库还是查询时不可见；
2. 对 BGE-small 重点核对 `chunks.jsonl`、构建日志和 bulk failure；对 Conan 核对对应的 chunk cache、分片状态及构建完成标记；
3. 在不改变 RAG 逻辑的前提下，只修复或重建缺失文档覆盖，再重跑 O3 dense/BM25 对比；
4. 覆盖修复前，不进行完整 F500 或 Conan 主流程替换测试。

复现实验脚本：`scripts/diag/audit_o32_gold_coverage.py`。
