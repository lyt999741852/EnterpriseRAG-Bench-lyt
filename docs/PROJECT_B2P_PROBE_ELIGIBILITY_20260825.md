# B2.P Project 锚点 Probe 资格检查

日期：2026-08-25（Asia/Shanghai）

## 结论

**未通过，停止 B2 Project 锚点路线。** 未发起重复的 live retrieval probe，也未修改 pipeline、索引、配置、RRF、rerank 或 PageIndex。

这一结论来自对冻结 AB50 PageIndex ON route trace 的只读检查。B2.P 原计划验证“保留题干 Project 实体、组件、路径/版本和硬约束”的查询是否改善 raw 覆盖；但用于该验证的完整题干和更细分的锚点查询已经在基线运行中实际执行。因此再次对相同 BGE 索引和模型执行会是重复实验，不能证明新的设计有效。

## 已执行的基线查询证据

| Question ID | 基线路由 | 已执行的相关查询 | 覆盖结论 |
|---|---|---|---|
| `qst_0350` | `project_related` | 完整原题已走 keyword/dense；另有 Northpeak/Dedicated Burst Usage 的 rewrite 与 answer-intent。 | raw 已命中 3/3 目标；问题是 rerank 后只保留 1/3，锚点增补不是独立修复。 |
| `qst_0356` | `constrained` | 完整原题已走 keyword/dense；还执行了 incident type、primary owner、time-to-mitigate、time-to-fix 的独立 hybrid 查询。 | raw 仍仅 2/4、submitted 1/4；不应以重复锚点查询掩盖多文档原始缺失和 selector 缺失。 |
| `qst_0362` | `project_related` | 完整原题已走 keyword/dense；还执行了 Python、TypeScript、Go 各自的 parity-matrix hybrid 查询。 | raw 仍仅 3/9、submitted 1/9；说明“保留 SDK 名称/版本/矩阵”本身不是尚未测试的变量。 |

`qst_0356` 被 LLM 推断为 `constrained`，而不是 `project_related`；该观察只说明问题文本路由可能是后续独立诊断主题，不能在本轮通过 benchmark 真实类型强制改路由。

## 处置

- 不新增 Project 锚点实现或 smoke 配置；不将已运行的原题/分面查询伪装为新 probe。
- `qst_0350` 的多文档 rerank 保留、`qst_0356/0362` 的多文档 raw 覆盖与 selector 缩减分别保留为未来独立任务候选，不能混合调参。
- 下一候选诊断转向 B3 Completeness：先对 AB50 的 completeness 题做与 B2 相同的逐文档阶段审计，再决定是否存在可隔离的证据覆盖改动。
