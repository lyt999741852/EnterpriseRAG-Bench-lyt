# B3.1 Question-planned Multi-document Smoke10

日期：2026-08-25（Asia/Shanghai）

## 结论

**未通过，停止 B3.1，不运行 AB50。**

实验仅在原计划为 `single_multisection`、题干规划至少 4 个独立分面、且硬约束明确包含多环境/多范围时，将证据模式提升为 `multi_hop`。候选文档、节点、hop、检索、reranker 和生成预算均保持原值；不使用 benchmark 真实题型、目标文档、答案或评分。

## 运行与触发

| 检查 | 结果 |
|---|---:|
| 固定题目数 / answers / traces | 10 / 10 / 10 |
| 官方 no-correction 完成题数 | 10 |
| Pipeline simple recall / invalid docs | 56.6 / 0.2 |
| 官方综合正确性×完整度 | 57.89 |

`qst_0447` 实际触发 B3.1：推断类型仍为 `intra_document_reasoning`，计划模式由 `single_multisection` 提升为 `multi_hop`，估计文档数由 1 提升为 6；候选文档、节点和 hop 预算保持 10/8/2。`qst_0432` 保持原 `exhaustive` 计划，未触发实验。

## 目标与控制结果

| Question ID | 正确 | 完整度 | 文档召回 | Extra | 与基线 |
|---|---:|---:|---:|---:|---|
| `qst_0447` | 否 | 0% | 0% | 1 | 无变化 |
| `qst_0432` | 是 | 0% | 50% | 0 | 无变化 |

`qst_0447` 触发后仍只选中与基线相同的一个非目标文档；模式提升没有改变 final/submitted 覆盖。其余 8 个 Basic、Project 和 InfoNotFound 控制题的官方逐题结果也与 AB50 基线相同。

## 处置

- 已精确回滚本地和远端 `src/pageindex_router.py` 的实验运行时代码；未留下默认行为变化。
- 保留独立配置、生成器、远端应用/回滚/启动脚本和本报告，用于复核失败实验。
- 不扩大候选预算、不调整 reranker，不在 B3 上继续叠加改动。
- 下一候选任务为 A3.A：对 A0 中 2 个 selector drop 和 4 个 generation gap 做逐题离线证据覆盖审计，先确认是否存在尚未测试的独立变量。

原始答案、trace、评分和审计 JSON 保留在忽略的 `outputs/b3_1_multidoc_smoke10_20260825/`，不纳入提交。
