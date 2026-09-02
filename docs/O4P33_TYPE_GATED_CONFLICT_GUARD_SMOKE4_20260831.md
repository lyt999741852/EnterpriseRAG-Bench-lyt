# O4.P3.3：仅 conflicting_info 启用生成 guard

日期：2026-08-31
分支：`codex/semantic-a0`
运行目录：`/opt/enterprise-rag-bench/app/outputs/pageindex_o4p33_type_gated_guard_smoke4_20260831`

## 目的与隔离

在 O4.P3.2 证明全局 guard 会使 `qst_0322` 控制题回退后，本轮将同一 conflict guard 限定在 `question_type=conflicting_info`。检索、软池、selector、BGE-small 只读索引、PageIndex、DPV4、并发和 `no-correction` 均保持不变；远端只使用临时 pipeline/generator 模块。

题集：`qst_0413`、`qst_0416`（conflicting_info）以及 `qst_0322`、`qst_0386`（控制题）。

## 官方评分结果

| 题目 | 类型 | correctness | completeness | recall | 结论 |
|---|---|---:|---:|---:|---|
| qst_0413 | conflicting_info | **正确** | 12.50% | 100.00% | 相比 P3.1 保持修复 |
| qst_0416 | conflicting_info | 正确 | 83.33% | 50.00% | 无回退 |
| qst_0322 | intra-document | 正确 | 100.00% | 100.00% | 恢复 P3.1 正确状态 |
| qst_0386 | constrained | 正确 | 100.00% | 100.00% | 无回退 |

汇总：correctness **100.00%**、completeness 73.96%、combined 73.96、document recall 87.50%、invalid extra docs 0.00；4/4 完成，0 跳过、0 correction。

## 关键诊断

题型限定解决了 P3.2 的副作用：两个控制题均恢复正确，`qst_0413` 也保持正确。其答案首句正确识别 cost-ops/Priya Desai 为 72h grace window 后的终止批准方。

但答案仍附带“infra manager 批准将 72h 改为 5 business days”等与该题 gold facts 不一致的额外断言。当前官方 DPV4 评分将其判为“extra context without conflicting”，因此本轮的 100% correctness 不能视为事实审计已完全通过，反而暴露了同一 DPV4 生成/评分链的偏置风险。

## 结论与下一步

1. guard 的作用域必须按题型限定；O4.P3.3 通过“冲突题修复、控制题无回退”这一结构性门槛。
2. 尚不应直接推广到 AB50/F500：`qst_0413` completeness 仅 12.5%，且仍有官方 judge 未识别的多余/矛盾事实。
3. 下一步 O4.P3.4：保留题型限定 guard，增加冲突题答案的确定性事实约束/独立裁判复核，要求 72h、cost-ops、未确认 infra-manager approval 三项同时满足，再复测冲突题 AB50。
