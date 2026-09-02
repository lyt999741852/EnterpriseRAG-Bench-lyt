# R11.E raw-miss 字段级检索对照（2026-08-28）

## 目的与方法

R11.D 已确认目标 chunk 存在但相关性分数不足。本实验不改 pipeline 或索引，针对现有 ES 映射中的 `title` 与 `text` 字段执行 top-1000 BM25 对照：balanced（`title^2,text`）、title-heavy（`title^8,text`）、cross-fields（AND）及 phrase+terms（标题短语加题干锚点）。评价仍只使用题干，期望文档仅用于离线计算目标排名。

## 结果

| profile | 5 题目标进入 top-1000 | 命中题目 |
|---|---:|---|
| title_text_balanced | 1/5 | `qst_0298` rank 879 |
| title_heavy | 1/5 | `qst_0298` rank 879 |
| cross_fields（AND） | 0/5 | — |
| phrase_or_terms | 2/5 | `qst_0231` rank 368；`qst_0298` rank 565 |

结果与 R11.D 的原题 BM25 1/5、锚点 BM25 2/5 完全一致。title 加权没有改变目标排名，cross-fields 因题干词不可能全部出现在同一 chunk 而全部失败；phrase+terms 只是复现锚点查询效果。

当前索引映射只有 `title`、`text` 两个全文字段，`file_path`、`source_type` 是 keyword 字段，不能提供通用的语义补召回。没有发现通过字段权重或简单布尔组合解决 raw-miss 的证据。

## 结论与后续

R11.E 不放行。字段级 BM25 调整不能改善 5 个 raw-miss，继续调整 title 权重、AND/OR 或短语规则预计只会在个别题目上改变排序，不能形成通用收益。

下一步应评估独立的文档表征：在隔离索引上对比当前 BGE-small 与可用 embedding 的重嵌入/字段拼接方案，或先做 chunk 文本规范化后重新建立小样本索引；任何 live Conan 1792 维向量必须与同维度重建索引配套，不能查询当前 BGE 384 维索引。
