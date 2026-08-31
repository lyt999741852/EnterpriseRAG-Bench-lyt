# O3.1：raw-miss 的索引覆盖 / BM25 / dense 分层诊断

日期：2026-08-31

## 目的与方法

O3 已在 46 道有效 raw-miss 上比较 BGE-small 与 Conan 的 dense 召回。O3.1 对同一批题追加三项只读检查：

1. gold `doc_id` 是否存在于对应索引；
2. 原始问题用 BM25（`text` 字段，top-1000）能否命中 gold 文档；
3. 复用 O3 的 dense top-1000 首个 gold rank。

不调用生成模型、改写、rerank、PageIndex，也不修改索引。分类优先判断索引是否存在：`index_missing`；存在后再分为 `dense_and_lexical`、`dense_only`、`lexical_only`、`both_miss`。

## 总体结果（46 题）

| 层级 | BGE-small | Conan |
|---|---:|---:|
| gold 文档存在的题目 | 23/46 | 32/46 |
| gold 文档不存在的题目 | 23/46 | 14/46 |
| dense 命中（O3 top-1000） | 5/46 | 4/46 |
| BM25 命中（top-1000） | 23/46 | 25/46 |
| `index_missing` | 23 | 14 |
| `dense_and_lexical` | 3 | 0 |
| `dense_only` | 0 | 2 |
| `lexical_only` | 12 | 17 |
| `both_miss`（索引中存在但两路都未命中） | 8 | 13 |

索引中的 gold 文档 ID 覆盖为 BGE 36/61、Conan 39/61。Conan 索引文档总量更大，但仍缺失 22 个有效 raw-miss 相关 gold 文档；因此“维度更高、文档更多”并不等价于 gold 覆盖完整。

## semantic 子集（35 题）

| 层级 | BGE-small | Conan |
|---|---:|---:|
| gold 文档存在的题目 | 19/35 | 26/35 |
| dense 命中 | 4/35 | 2/35 |
| BM25 命中 | 17/35 | 17/35 |
| `index_missing` | 16 | 9 |
| `lexical_only` | 10 | 13 |
| `both_miss` | 6 | 11 |

semantic 题中 Conan 的索引覆盖较好，但 dense 命中更少、`both_miss` 更多；这解释了 O3 中 Conan semantic @1000 仅 5.71%，低于 BGE 的 11.43%。

## 诊断结论

### 1. 首要问题是索引覆盖不一致

BGE 的 46 道题中有一半 gold 文档不在当前索引，Conan 仍有约三成缺失。对于 `index_missing`，任何 embedding、rerank 或路由优化都不可能恢复正确证据；必须先核对 F500 使用的数据快照、文档过滤和索引构建范围。

### 2. 对已存在文档，BM25 是有效托底，dense 不是

BGE 的 23 道索引内题中，BM25 命中 23 道，而 dense 仅命中 5 道；Conan 分别为 25 道和 4 道。说明原始问题直接 dense 查询对这批困难题不稳定，但词法路径能找回相当一部分候选。此前 O2 的“保留原始 lexical/dense 候选”方向有证据基础，应该优先做通用候选并集，而不是题目级关键词扩充。

### 3. 仍存在真正的双路失败

BGE 有 8 道、Conan 有 13 道在索引存在的前提下同时 BM25 与 dense 未命中。这部分才是 embedding 语义表达、切块边界、字段分析或 gold 标注映射的候选问题，需要逐题查看文本和 chunk，而不能用整体平均分判断。

## O3.2 建议

先做索引一致性核验：将 61 个 gold 文档 ID 与 F500 实际语料清单、索引构建 manifest、过滤规则做集合差异；同时抽取 `index_missing` 的文档来源。只有覆盖问题修正后，再在“索引存在且 BM25 命中、dense 未命中”的 `lexical_only` 子集做通用 dense+BM25 候选并集 smoke，并以控制题回归验证是否引入噪声。

复现实验脚本：`scripts/diag/diagnose_o31_raw_miss_layers.py`。
