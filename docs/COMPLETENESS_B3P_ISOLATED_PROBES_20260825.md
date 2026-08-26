# B3.P Completeness 两条隔离只读诊断

日期：2026-08-25（Asia/Shanghai）

## 路径一：`qst_0432` selector/citation 覆盖

**不放行实现。** 该题的 PageIndex 计划已经是 `exhaustive`：估计 6 个文档、候选上限 24、节点上限 24；rerank 后 6 个目标文档的位次为 1、2、4、5、8、11。即 raw 和 rerank 都不是瓶颈。

后续仍发生了覆盖缩减：final 为 5/6、submitted 为 3/6。PageIndex 选择了 6 个文档，其中 5 个是目标文档；因此问题在 evidence-selection / citation 之后。B1 的受证据事实清单 smoke 已经没有改善生成覆盖，不能把该失败重复包装成 B3 的检索改动。

## 路径二：`qst_0447` 多文档过程问题

**放行一个候选实现，但尚未实施。** 题干明确要求 Hosted + Dedicated 的完整端到端过程，并列出审批、checklist、rollout/rollback、客户沟通等独立分面。基线的 `search_plan` 也从题干产生了六个分面和四个对应检索查询，后续还产生了十个 follow-up 查询；没有使用 benchmark 真实类型。

但同一题被 LLM 推断为 `intra_document_reasoning`，PageIndex 计划为 `single_multisection`（估计 1 个文档、候选上限 10、节点上限 8）。raw 的 4 个目标文档在 rerank 前分别位于第 4、13、20、27 位，rerank 后仅保留第 4 位文档，最终选中的是一个非目标文档，final/submitted 均为 0。

这构成一个可隔离的、问题文本驱动的变量：**当 PageIndex 已从题干规划出多个独立分面及多环境硬约束时，不能仍按单文档模式执行。** 候选 B3.1 可以依据现有 `search_plan` 的分面数与硬约束决定多文档证据计划；不读取 `expected_doc_ids`、真实题型、答案或评分结果，不改变检索权重、候选预算或 reranker。

## B3.1 门禁

1. 仅在题干规划出的多分面/多环境条件满足时激活，不以 `completeness` 标签强制路由。
2. 先运行包含 `qst_0447`、`qst_0432` 及非 Completeness 对照题的固定单并发 smoke。
3. 通过条件：`qst_0447` final/submitted 目标文档覆盖提升；`qst_0432` 不恶化；无额外文档上升；官方 no-correction 评分完成。
4. 不通过则精确回滚该开关，不运行 AB50。
