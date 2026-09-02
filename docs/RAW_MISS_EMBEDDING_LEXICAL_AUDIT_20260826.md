# Raw-miss embedding / 索引覆盖与词法锚点诊断（2026-08-26）

## 范围与方法

对 AB50 conflict-contract + generation-guard 固定轨迹中的 5 道 `raw_miss`（`qst_0116`、`qst_0184`、`qst_0231`、`qst_0251`、`qst_0298`）执行只读诊断：

1. 查询 BGE ES `enterprise-rag-bge-small-v1`，确认目标 `doc_id` 的 chunk 是否存在及 embedding model。
2. 使用 pipeline 同版本的 `BAAI/bge-small-en-v1.5`（384 维）生成问题向量，执行 ES dense top-200 探针，并读取目标 chunk 的直接 cosine 分数。
3. 用原题和仅由题干抽取的实体/版本/数字/长词锚点执行 BM25 top-200 探针。

探针不写入 ES、不修改索引、不接入主链。live Conan embedding API 返回 1792 维，与 BGE ES 的 384 维不兼容，故不把该 API 混入 BGE dense 结果；其维度差异仅作为环境检查记录。

## 结果

| 题目 | 索引目标 chunks | 目标 embedding model | 目标 dense 分数（最高） | dense top-200 最低分 | BM25 原题/锚点 top-200 | 题干锚点在目标文本 |
|---|---:|---|---:|---:|---|---:|
| qst_0116 | 2 | BGE-small | 0.7835 | 0.9046 | 均未命中 | 3/6 |
| qst_0184 | 2 | BGE-small | 0.6850 | 0.8957 | 均未命中 | 5/12 |
| qst_0231 | 2 | BGE-small | 0.7224 | 0.8953 | 均未命中 | 11/20 |
| qst_0251 | 1 | BGE-small | 0.7178 | 0.8943 | 均未命中 | 3/17 |
| qst_0298 | 4 | BGE-small | 0.7164 | 0.8806 | 均未命中 | 8/14 |

汇总：

- 索引覆盖 **5/5**；目标 chunk 数为 1–4，且全部标记为 `BAAI/bge-small-en-v1.5`，排除“索引缺文档/模型字段缺失”。
- 同模型 dense top-200 命中 **0/5**。目标最高分比 top-200 边界低约 0.10–0.21，候选池从 120 扩至 180 不足以跨越该差距。
- BM25 原题与抽取锚点 top-200 均 **0/5**。其中 qst_0231 等目标文本有较多词面重叠，仍未进入高排名，表明词面重叠不足以克服长文本/主题相似噪声。
- live embedding API 为 1792 维 Conan，而当前 BGE ES 为 384 维；不能用该 API 向量直接查询此索引，必须保持模型与索引一致。

## 结论与后续

本组 raw miss 的第一原因是查询—目标文档相关性排序不足（dense 与 BM25 同时低排名），不是 PageIndex、selector 或额外文档过滤。下一步优先做离线词法实体/数字/版本分解和 query-document 表征诊断，评估“低权重 lexical anchor 候选”是否能把目标文档带入候选集；不得锁定目标 `doc_id`，也不直接接入 live 1792 维 embedding。只有在小样本确认目标候选存活且控制题无回退后，才考虑主链 smoke；F500 继续停止。

完整机器可读结果：`outputs/raw_miss_embedding_lexical_audit.json`。
