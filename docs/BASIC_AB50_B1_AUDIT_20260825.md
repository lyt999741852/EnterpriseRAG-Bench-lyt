# B1 Basic 覆盖审计（AB50 PageIndex ON）

日期：2026-08-25（Asia/Shanghai）

基线：`pageindex_ab50_semantic_consensus_20260820_r3_on`，综合分 59.34。

## 离线分桶

| 类别 | 题数 | 含义 |
|---|---:|---|
| 完全成功 | 11 / 18 | 正确性、完整性、文档召回均为 100%。 |
| Generation coverage gap | 3 / 18 | 目标文档已提交、答案正确、无额外文档，但完整性低于 100%。 |
| Retrieval/citation gap | 4 / 18 | 文档召回低于 100%，不属于本轮生成覆盖改动的目标。 |

三个 generation coverage 样本的完整性分别为 80%、75% 和 50%，全部具备 100% 文档召回、1 个提交文档、0 无效额外文档。这说明 B1 可以在不调整检索权重和候选集的前提下，测试答案前的受证据约束事实清单。

## B1.1 设计门禁

- 仅在 LLM 推断为 `basic` 的路由启用；不使用 benchmark 真实题型。
- 不修改 BM25、dense、RRF、rerank、PageIndex、chunk 或候选预算。
- 清单只枚举问题中明确请求的事实槽位；最终答案只能从已选证据中补足，不能猜测。
- 首先使用包含上述 3 个样本和对照题的固定 10 题串行冒烟；检查答案、trace、checkpoint 和 extra docs。
- 仅当 Basic 完整性改善、AB50 不低于 59.34 的可接受波动区间、InfoNotFound 不误答且 extra 不增加时，才运行完整 AB50 与官方 no-correction 评分。
