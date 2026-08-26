# A3.5 generation conflict guard 与 AB50 回归（2026-08-26）

## 优化机制

本轮不是放宽 strict selector，也没有删除阻断性冲突检查，而是分两层处理：

1. selector 输出契约要求：经过明确的最终/当前/规范/适用来源优先级后已经解释的差异写入 `resolved_conflicts`；同等权威且仍未解决的矛盾继续写入 `conflicts`。
2. generation 与 final-answer audit 提示词增加答案保护：若已接纳证据直接回答题干分面，应保留并优先输出该直接值；不同范围或更宽时间线的证据只能作为限定，不能把直接值改写成无答案/不确定。

解析器仍对非空阻断性 `conflicts` fail-closed，因此安全边界未改变。`resolved_conflicts` 只是避免已解决差异触发 strict selector 清空有效证据。

## 验证

### 六题隔离生成回归

固定 A3.4 route trace，绕过检索与 reranker，只重跑 generation/final audit：

- 6 题完成，正确性 5/6，完整性 66.67%，combined 66.67，recall 58.33%。
- `qst_0298` 生成恢复为直接答案：HSM provisioning 在需要硬件时为 2–4 周；不再把组件工期改写成总环境工期未知。
- `qst_0272` 保持恢复；`qst_0184` 为冻结控制题，继续错误，未出现控制放宽。

### PageIndex ON AB50

配置：`configs/eval_pageindex_ab50_semantic_conflict_guard_r3_20260826.yaml`，50/50 完成，官方 no-correction：

| 指标 | 冻结基线 r3_on | conflict contract r2 | generation guard r3 | 相对基线 |
|---|---:|---:|---:|---:|
| correctness | 64.00% | 64.00% | **64.00%** | 0.00 pp |
| completeness | 65.15% | 65.81% | **66.50%** | +1.35 pp |
| combined | **59.34** | 59.01 | **59.41** | +0.07 |
| document recall | 61.76% | 63.89% | **63.89%** | +2.13 pp |
| invalid extra docs | 0.17 | 0.19 | **0.19** | 仅诊断 |

`qst_0272` 继续由 selector contract 恢复；`qst_0298` 在完整 AB50 中仍为 false/50%（相对基线的单题回归尚未完全消除），说明长上下文下 generation guard 的效果不稳定，后续可做定向单题提示词/证据裁剪，但不阻断本轮整体合流。额外文档指标未作为独立门槛。

## 远端清理与结论

- AB50 完成后已回滚 A3.5 generation guard 与 A3.2 selector contract 临时 runtime 补丁。
- `src/generator.py` 重新通过 `py_compile`，两份备份文件均已删除。
- A4/B4 以“combined 不低于 59.34、整体 correctness 不下降”为门槛，本轮通过；F500 尚未启动，作为下一步独立任务。
