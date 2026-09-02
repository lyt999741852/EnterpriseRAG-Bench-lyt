# R11.C 条件式 structured reserve smoke（2026-08-27）

## 目的

R11.B 的 route-independent structured query 对所有题增加候选，但低权重 RRF 没有把目标候选稳定送入 reranker。本实验只在原始 keyword/dense 前 8 个文档没有交集时触发 structured query，并将每个 structured view 截断为 40 条；原始候选仍保留 12 个 reserve，且每文档最多 2 个 chunk。实验不使用答案、期望文档或人工关键词。

## 配置与执行

- 题目：R11.B 相同的 5 个 raw-miss（`qst_0116/0184/0231/0251/0298`）和 4 个控制题（`qst_0093/0211/0272/0356`）。
- structured 触发：原始 keyword/dense top-8 文档交集小于 1；候选 top-40；低权重 0.22；原始 reserve 12。
- 远端使用既有 Elasticsearch/BGE-small 索引、LLM `lark`、reranker 服务；pipeline 并发 2；官方评分使用 `--no-correction`。
- 运行结束后依次回滚 R11.C、R11.B 临时 patch，并通过 `py_compile`。

## 结果

| 指标 | R11.B r2 | R11.C | 变化 |
|---|---:|---:|---:|
| correctness | 22.22%（2/9） | 22.22%（2/9） | 0 |
| completeness | 33.33% | 27.78% | -5.56pp |
| combined | 22.22 | 22.22 | 0 |
| document recall | 13.89% | 11.11% | -2.78pp |
| invalid extra | 0.67 | 0.56 | -0.11 |

逐题变化：`qst_0211`、`qst_0298` 继续正确；`qst_0116` 虽进入 raw views，仍在 pre-rerank 丢失；`qst_0184/0231/0251` 仍 raw-miss。控制题 `qst_0356` 从 R11.B 的 completeness 50%、recall 25% 回退为 0%，`qst_0272` 仍未恢复。

离线事实漏斗（9 题）为 `raw_miss=4`、`rerank_drop=2`、`citation_or_selector_drop=2`、`fully_successful=1`；首个事实损失为 raw views 7、pre-rerank 2、submitted 5，说明候选覆盖和 reranker/提交层仍是主要瓶颈。

## 结论与后续

R11.C 不放行。低一致门控减少了无条件 structured 调用，但没有改善核心 raw-miss；同时候选截断/合流改变了控制题证据组成，造成 `qst_0356` 回退。因此暂不继续调 structured 表示、路由标签或扩大其权重，也不运行 AB50/F500。

下一步转向 R11.D：对 5 个 raw-miss 做 embedding/索引覆盖、dense/BM25 分数与 top-N 边界的只读诊断，并核对是否存在索引字段、分词或向量空间不匹配；只有确认通用检索候选能稳定覆盖后，才重新设计候选保留策略。
