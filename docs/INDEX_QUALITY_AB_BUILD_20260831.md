# 索引质量 A/B 小型对照索引

日期：2026-08-31

## 目的与范围

针对 O0 的 46 道有效 raw-miss，提取涉及的 61 个 gold 文档，使用同一 `BAAI/bge-small-en-v1.5` 建立两套隔离 ES 索引。两套索引不接入现有 RAG 主链，仅用于后续 Recall@K 对照。

## 两个变体

| 变体 | 表征文本 | 切块 | 索引 |
|---|---|---|---|
| A | 原始 `text` | whitespace 512 token，overlap 0 | `o34_quality_a_bge_small_20260831` |
| B | `source_path + title + 首行 section_context + text` | whitespace 448 token，overlap 64 | `o34_quality_b_bge_small_20260831` |

## 构建结果

| 指标 | A | B |
|---|---:|---:|
| 文档数 | 61 | 61 |
| chunks | 120 | 149 |
| ES count | 120 | 149 |
| ES health | green | green |
| 向量维度 | 384 | 384 |
| embedding model | `BAAI/bge-small-en-v1.5` | `BAAI/bge-small-en-v1.5` |

B 版本抽样记录确认前缀已写入，例如 `source_path`、由文件名生成的 `title` 和首行频道/章节上下文均出现在 embedding 文本中。两套索引都显式保存 `title`、`section_path`、`raw_text`、`chunk_index` 和字符偏移，便于后续解释召回差异。

机器可读构建记录：`/opt/enterprise-rag-bench/app/outputs/pageindex_full500_bge_dpv4_20260831/index_quality_ab_build_20260831.json`。

## 后续

下一步在同一 46 题上分别查询 A/B，比较 doc-level Recall@30/120/240/1000，并记录目标 chunk rank、BM25 命中和 query 延迟。只有 B 在 raw-miss 上稳定提升且控制题不回退，才考虑全量重建；本轮尚未修改生产索引。
