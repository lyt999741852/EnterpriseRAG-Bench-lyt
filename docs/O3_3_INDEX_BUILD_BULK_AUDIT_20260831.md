# O3.3：索引构建日志与 bulk failure 核查

日期：2026-08-31

## 检查范围

只读检查 BGE-small 与 Conan 的 preprocess metadata、`chunks.jsonl`/`failed_files.jsonl`、ES build report、Conan 构建日志、resume progress，以及目标索引级 health。没有重建索引或写入 ES。

## BGE-small

- preprocess：511,957 docs、928,534 chunks、`failed_files=0`；
- 首次构建：918,528 chunks 新写入，10,000 已存在，`failed=0`；
- 后续幂等/碰撞修复：`es_count=928,534`（修复报告曾短暂显示 928,536），最终 report 仍为 `failed=0`；
- `failed_files.jsonl` 为空；
- 目标索引 `enterprise-rag-bge-small-v1` 当前索引级 health 为 green，1 个 primary、无未分配分片。

没有发现 BGE bulk failure 或文档入库中断证据。

## Conan 1792 维

- preprocess：511,957 docs、3,030,317 chunks、`failed_files=0`；
- `es_build_progress.json`：`progress_percent=100`、`remaining_chunks=0`、`failed=0`；
- 最终 `es_count=3,030,317`，与 cache chunk 数一致；
- 目标索引 `enterprise-rag-qwen3-emb-v3-conan448` 当前索引级 health 为 green，16 个 primary、无未分配分片；
- 构建日志没有 `bulk indexing failed`、`failed>0` 或 ES bulk 错误。

日志中出现 3 次 traceback，均为 embedding API 的 `TimeoutError: timed out`，发生在构建中途约 55 万、149 万和 248 万 examined chunks 的位置。每次中断后都重新加载 cache 并从 progress offset 继续，最终完成；这属于可恢复的 embedding 服务超时，不是 ES bulk 丢文档。

## 与 O3.1/O3.2 的一致性

修正 terms 查询后，61/61 gold doc_id 在 corpus、manifest 和两套 ES 中均存在。O3.1 的有效 raw-miss 分层为：

| 层级 | BGE-small | Conan |
|---|---:|---:|
| dense_and_lexical | 5 | 1 |
| dense_only | 0 | 3 |
| lexical_only | 18 | 24 |
| both_miss | 23 | 18 |

因此 raw-miss 的主因是 gold chunk 未进入 dense/BM25 top-1000，而不是索引构建时缺失文档。

## 结论与后续

1. **不需要为修复所谓“缺失文档”而重建当前两个索引。** 现有索引完整、目标分片健康、bulk failure 为零。
2. **Conan 构建稳定性需要单独关注。** embedding API 曾发生 3 次超时；后续若重建，应保留 resume/checkpoint，并降低并发或增加 API 超时/重试，避免重复计算。
3. **检索优化优先级不变。** 继续针对 `lexical_only` 和 `both_miss` 做通用候选并集、切块边界与字段分析；Conan 在 O3 semantic dense 召回未超过 BGE，不直接替换主流程。

复现实验脚本：`scripts/diag/audit_o33_index_build.py`。
