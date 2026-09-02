# O4.P3.1：conflicting_info 契约单变量 smoke

日期：2026-08-31
分支：`codex/semantic-a0`
运行目录：`/opt/enterprise-rag-bench/app/outputs/pageindex_o4p31_conflict_smoke4_20260831`

## 目的与隔离

本轮针对 O4.P3 50 题中 `qst_0413` 的回退做最小回归。保持 BGE-small 索引、切块、BM25+dense+rerank、PageIndex、O4.P3 软池、DPV4、并发和 `no-correction` 完全不变，仅在临时 generator 模块的 precision selector JSON 契约中增加：

- `resolved_conflicts` 字段；
- 明确的最终/当前/适用来源优先级；
- 只有同等权威且无法消解的矛盾才进入阻断性 `conflicts`。

题集为冲突题 `qst_0413`、`qst_0416`，以及控制题 `qst_0322`、`qst_0386`。修改在临时模块中完成，远端原始 `src/generator.py` 未被覆盖。

## 评分结果

| 题目 | 类型 | correctness | completeness | recall | 结论 |
|---|---|---:|---:|---:|---|
| qst_0413 | conflicting_info | **错误** | 12.50% | 100.00% | 仍把 infra manager/5 business day 当作批准结论 |
| qst_0416 | conflicting_info | 正确 | 83.33% | 50.00% | 无回退 |
| qst_0322 | intra-document | 正确 | 100.00% | 100.00% | 控制题稳定 |
| qst_0386 | constrained | 正确 | 100.00% | 100.00% | 控制题稳定 |

汇总：correctness 75.00%、completeness 73.96%、combined 70.83、document recall 87.50%、invalid extra docs 0.00。生成和评分均完成，0 跳过、0 correction。

## 诊断

`qst_0413` 的 document recall 为 100%，目标文档已进入最终候选；因此不是 raw-miss。答案仍错误，且输出声称 infra manager 批准、把 72h 改成 5 business days，与官方事实约束相反。selector 契约没有消除该错误，说明失败点位于：

1. 同一文档内不同作用域/角色的冲突事实判别；或
2. fact verification / final answer audit 对已选证据的再解释。

两个控制题未回退，说明新增契约没有造成通用链路破坏，但也不足以作为 F500 放行依据。

## 下一步

继续 O4.P3.2 生成阶段 guard 单变量 smoke：保持同一 4 题、同一 O4.P3 检索和 selector，仅增加“直接回答问题作用域的证据优先、不同作用域不得覆盖、保留 72h 和 cost-ops”规则，验证能否修复 `qst_0413` 且不影响控制题。若仍失败，再做答案前的证据片段/selector 原始 JSON 追踪，而不是继续扩大候选池。
