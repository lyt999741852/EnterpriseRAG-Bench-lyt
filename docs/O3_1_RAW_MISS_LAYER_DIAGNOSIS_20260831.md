# O3.1：raw-miss 的 BM25 / dense 分层诊断

日期：2026-08-31

## 方法

针对 O0 的 46 道有效 raw-miss，检查 gold `doc_id` 是否存在于 BGE-small/Conan ES 索引，并比较原始问题的 BM25 top-1000 命中与 O3 dense top-1000 命中。索引存在性使用按 `doc_id` collapse 的 terms 查询，避免多 chunk 文档占满结果窗口。

本实验不调用生成模型、改写、rerank、PageIndex，也不修改索引。

## 结果（46 题）

| 指标 | BGE-small | Conan |
|---|---:|---:|
| gold 文档在 ES 中存在 | 46/46 | 46/46 |
| dense 命中（O3 top-1000） | 5/46 | 4/46 |
| BM25 命中（top-1000） | 23/46 | 25/46 |
| `dense_and_lexical` | 5 | 1 |
| `dense_only` | 0 | 3 |
| `lexical_only` | 18 | 24 |
| `both_miss` | 23 | 18 |

### semantic 子集（35 题）

| 指标 | BGE-small | Conan |
|---|---:|---:|
| dense 命中 | 4/35 | 2/35 |
| BM25 命中 | 17/35 | 17/35 |
| `dense_and_lexical` | 4 | 0 |
| `dense_only` | 0 | 2 |
| `lexical_only` | 13 | 15 |
| `both_miss` | 18 | 16 |

## 诊断结论

1. **不存在 gold 文档缺失。** 之前的 `index_missing` 统计是批量 terms 查询未按唯一 `doc_id` 折叠造成的假象，已在脚本中修正；O3.2/O3.3 均以修正版结果为准。
2. **BM25 是有效托底。** 在索引存在的前提下，BM25 能命中 23/46（BGE）和 25/46（Conan），明显高于 dense 的 5/46 和 4/46。
3. **Conan 未改善 semantic dense 召回。** semantic 子集 Conan dense 命中 2/35，BGE 为 4/35；Conan 的优势仅体现在少量 lexical/basic 题。
4. **真正的 embedding/字段难题是 `both_miss`。** BGE 23 题、Conan 18 题在索引存在时两路均未命中，应进一步查看切块边界、字段分析和 gold 标注映射。

## 后续

先完成 O3.3 的构建链路核查；确认索引完整后，再对 `lexical_only` 与 `both_miss` 做通用候选并集和 chunk 级审计，不进行题目级关键词硬编码。

复现实验脚本：`scripts/diag/diagnose_o31_raw_miss_layers.py`。
