# Semantic A1 Bridge Probe（失败）

日期：2026-08-25（Asia/Shanghai）

## 试验范围

- 输入：A0 离线分桶确定的 9 道 `raw_miss` 题。
- 查询：每题由 LLM 基于**问题文本本身**生成 1 条受约束的 bridge query；提示词禁止回答、猜测事实、引入未出现的同义词或文档名。
- 检索：主线 BGE ES 的只读 dense retrieval，候选预算与 S1 reranker 输入保持一致。
- 评估：仅在检索结束后，将候选与离线 gold document 做命中对比；gold 没有输入到 LLM 或检索器。

## 结果

| 指标 | 值 |
|---|---:|
| Raw-miss 题数 | 9 |
| 有效 bridge query | 9 |
| 目标文档命中 | 0 |
| 命中率 | 0.0% |

所有 9 条 bridge query 均正常生成，因而该结果不是 LLM 调用或空查询故障。它表明：仅将题干已有关系重述为单条自然语言查询，不能补回 BGE 主线漏掉的目标文档。

## 决策

按 A1 失败规则，停止该 bridge 路径：不创建 RRF 集成 YAML、不运行 10 题或 30 题主链实验、不与 selector/generation 改动叠加。原始 probe JSON 保留在实验输出目录供离线审计，不纳入 Git。

下一条可执行路线是 B1（Basic 覆盖审计），它与失败的 Semantic bridge 路线隔离。
