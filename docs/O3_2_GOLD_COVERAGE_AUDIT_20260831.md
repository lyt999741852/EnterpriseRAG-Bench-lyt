# O3.2：gold 文档覆盖链路审计

日期：2026-08-31

## 审计范围

针对 O0 的 46 道有效 raw-miss，展开 61 个 gold `doc_id`，只读核对 corpus、两套 manifest 与 ES 索引的集合关系，并确认 F500 配置实际使用的索引。

## 结果

| 环节 | BGE-small | Conan |
|---|---:|---:|
| gold 文档数 | 61 | 61 |
| corpus TXT 存在 | 61/61 | 61/61 |
| manifest 记录存在 | 61/61 | 61/61 |
| manifest 状态为 `chunked` | 61/61 | 61/61 |
| ES 中实际存在（按唯一 doc_id collapse） | 61/61 | 61/61 |

F500 配置 `configs/eval_pageindex_full500_bge_dpv4_20260831.yaml` 使用 `corpus/all_documents`、索引 `enterprise-rag-bge-small-v1`、manifest `.index_cache/full_es_bge_small/manifest.sqlite3`，并设置 `read_existing_index=true`、`overwrite_index=false`。

## 重要更正

O3.2 初版使用按 chunk 返回的批量 terms 查询，`size=61` 会被多 chunk 文档占满，错误地将部分 doc_id 标为缺失。修正版使用 `collapse: {field: doc_id}`，确认两套 ES 均包含全部 61 个 gold 文档。因此 O3/O3.1 的 `index_missing` 不是实际数据缺失，相关统计已在 O3.1 修正版中更正。

## 结论

raw-miss 的主因不是 corpus、manifest 或 ES 覆盖缺失，而是索引中存在 gold 文档时，原始问题的 dense/BM25 排名仍未把对应 chunk 置于 top-1000。下一步应聚焦切块边界、字段分析、查询表达和通用候选并集；不需要先重建索引来修复所谓的“缺失文档”。

构建日志与 bulk 状态由 O3.3 进一步核查。

复现实验脚本：`scripts/diag/audit_o32_gold_coverage.py`。
