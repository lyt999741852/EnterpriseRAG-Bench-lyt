# O3.1：raw-miss 的 BM25 / dense 分层诊断

日期：2026-08-31

## 方法

针对 O0 的 46 道有效 raw-miss，检查 gold `doc_id` 是否存在于 BGE-small/Conan ES 索引，并比较原始问题的 BM25 top-1000 命中与 O3 dense top-1000 命中。另读取 O0 的 `stage_document_ids`，核对 gold 是否在 raw、rerank、最终候选和提交证据阶段被保留。索引存在性使用按 `doc_id` collapse 的 terms 查询，避免多 chunk 文档占满结果窗口。

本实验不调用生成模型、改写、rerank 或 PageIndex，也不修改索引；候选保留字段仅是对既有 O0 运行轨迹的离线读取。

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

两个索引中的 61 个唯一 gold 文档均存在；因此 46 题不存在索引覆盖缺失。BGE 的 BM25 top-1000 命中 23/46、dense 命中 5/46；Conan 分别为 25/46 和 4/46。Conan 多出的 lexical 命中没有转化为 semantic dense 优势。

### semantic 子集（35 题）

| 指标 | BGE-small | Conan |
|---|---:|---:|
| dense 命中 | 4/35 | 2/35 |
| BM25 命中 | 17/35 | 17/35 |
| `dense_and_lexical` | 4 | 0 |
| `dense_only` | 0 | 2 |
| `lexical_only` | 13 | 15 |
| `both_miss` | 18 | 16 |

### O0 候选保留复核（BGE 主链）

| 阶段 | gold 文档被保留的题数 |
|---|---:|
| `raw_views` | 0/46 |
| `pre_rerank` | 0/46 |
| `post_rerank` | 0/46 |
| `final_before_generation` | 3/46 |
| `submitted` | 2/46 |

3 道后续出现的题为 `qst_0191`、`qst_0260`、`qst_0298`；其中 `qst_0191`、`qst_0298` 最终提交，`qst_0260` 在生成前后证据提交阶段丢失。该现象说明 PageIndex/候选扩展偶尔能从 raw-miss 中恢复文档，但当前 admission/提交仍不稳定。

## 诊断结论

1. **不存在 gold 文档缺失。** 两个索引均覆盖 46 题涉及的全部 61 个 gold 文档；之前的 `index_missing` 统计是批量 terms 查询未按唯一 `doc_id` 折叠造成的假象，已在脚本中修正；O3.2/O3.3 均以修正版结果为准。
2. **BM25 是有效托底。** 在索引存在的前提下，BM25 能命中 23/46（BGE）和 25/46（Conan），明显高于 dense 的 5/46 和 4/46。
3. **Conan 未改善 semantic dense 召回。** semantic 子集 Conan dense 命中 2/35，BGE 为 4/35；Conan 的优势仅体现在少量 lexical/basic 题。
4. **真正的 embedding/字段难题是 `both_miss`。** BGE 23 题、Conan 18 题在索引存在时两路均未命中，应进一步查看切块边界、字段分析和 gold 标注映射；这不是简单重建索引即可解决的问题。
5. **候选保留仍是独立损失层。** 虽然 raw/pre/post 均未命中，仍有 3 题在最终候选阶段恢复，且只有 2 题进入提交证据，说明后续应区分“扩展成功”和“admission/提交丢失”，不能把所有失败归咎于 dense。

## 后续

完成 O3.3 构建链路核查后，优先对 `lexical_only` 与 `both_miss` 做通用候选并集和 chunk 级审计；对 `final_before_generation`→`submitted` 的丢失单独检查 admission 规则，不进行题目级关键词硬编码。

复现实验脚本：`scripts/diag/diagnose_o31_raw_miss_layers.py`。
