# O4.P3.2：生成阶段 conflict guard smoke

日期：2026-08-31
分支：`codex/semantic-a0`
运行目录：`/opt/enterprise-rag-bench/app/outputs/pageindex_o4p32_generation_guard_smoke4_20260831`

## 目的与隔离

本轮以 O4.P3 的检索、软池、selector、BGE-small 只读索引、PageIndex、DPV4 和 `no-correction` 为基线，仅在临时 generator 模块的 fact verification 与 final answer audit 提示词中加入 conflict guard：

- 已有证据直接回答问题时，优先保留该作用域的值；
- 不因不同部署作用域或更宽时间范围的证据而覆盖直接回答；
- 对“被告知/报告/提议”的值保留其作用域。

selector 契约没有增加 `resolved_conflicts`，以便单独测量生成阶段 guard。题集仍为 `qst_0413`、`qst_0416`、`qst_0322`、`qst_0386`。

## 评分结果

| 题目 | 类型 | correctness | completeness | recall | 与 O4.P3.1 对比 |
|---|---|---:|---:|---:|---|
| qst_0413 | conflicting_info | **正确** | 62.50% | 100.00% | 错误→正确，修复生效 |
| qst_0416 | conflicting_info | 正确 | 83.33% | 50.00% | 保持正确 |
| qst_0322 | intra-document | **错误** | 50.00% | 100.00% | 正确→错误，控制题回退 |
| qst_0386 | constrained | 正确 | 100.00% | 100.00% | 保持正确 |

汇总：correctness 75.00%、completeness 73.96%、combined 61.46、document recall 87.50%、invalid extra docs 0.00。4/4 生成并评分，0 跳过、0 correction。

## 诊断

`qst_0413` 的答案被收敛为“cost-ops approves termination once the grace window expires”，不再错误声称 infra manager 或 5 business days，证明生成阶段 guard 可以修复前一轮发现的作用域覆盖问题；该题 document recall 始终为 100%，所以修复不是检索召回带来的。

同时，`qst_0322` 在同一 guard 下变为“evidence does not specify”并漏掉明确的 `runtime.bandwidth_fanout.enabled`，说明当前 guard 写在全局 fact verification/final audit 规则中，改变了非冲突题的保守性/取舍。故本轮不能作为全局 guard 放行。

## 结论与下一步

1. 生成阶段是 `qst_0413` 剩余错误的关键层，方向正确。
2. guard 必须按 `question_type=conflicting_info` 条件启用，不能作为所有题型的全局提示词规则。
3. 下一轮 O4.P3.3 只对 conflicting_info 注入同等 guard，使用同一 4 题验证 `qst_0413` 保持正确且 `qst_0322/qst_0386` 无回退；若通过，再扩展到冲突题 AB50。
