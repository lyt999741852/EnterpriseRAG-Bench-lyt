# O4.P3.4：冲突题 AB50 双裁判复测

日期：2026-08-31
分支：`codex/semantic-a0`
运行目录：`/opt/enterprise-rag-bench/app/outputs/pageindex_o4p34_conflict_ab50_20260831`

## 目的与隔离

本轮使用与 O4.P3 相同的 BGE-small 只读索引、切块、BM25+dense+rerank、PageIndex、软候选池和 `no-correction` 口径，仅把 O4.P3.4 的冲突题确定性事实约束扩展到此前的 balanced AB50。答案统一由 DPV4 生成，然后分别由 DPV4 和独立 Qwen/Lark 裁判评分。这样可以把生成改动与同模型自评偏差分开观察。

配置文件：`configs/eval_pageindex_o4p34_conflict_ab50_20260831.yaml`
答案并发：4；题数：50；索引文档数：928,534。

## 结果

| 裁判/基线 | correctness | completeness | combined | recall | invalid extra |
|---|---:|---:|---:|---:|---:|
| BGE-small 既有基线（DPV4） | 68.00% | 71.37% | 62.13 | 70.39% | 0.17 |
| AB50，DPV4 裁判 | **78.00%** | **76.11%** | **71.20** | **76.12%** | 0.21 |
| AB50，Qwen/Lark 独立裁判 | 68.00% | 68.61% | 59.68 | 76.12% | 0.21 |

相对既有基线，DPV4 裁判统计为 correctness +10.00 pp、completeness +4.74 pp、combined +9.07、recall +5.73 pp；但独立 Qwen/Lark 对同一答案的 correctness 没有提升，combined 反而低 2.45。两裁判逐题 correctness 一致 45/50（90%），不一致的 5 题全部是 DPV4 判正确、Qwen 判错误：`qst_0013`、`qst_0093`、`qst_0271`、`qst_0322`、`qst_0447`。没有出现 Qwen 判正确而 DPV4 判错误的题目。

## 冲突题专项

| 题目 | DPV4 | Qwen/Lark | recall | 观察 |
|---|---:|---:|---:|---|
| `qst_0413` | correct，completeness 62.50% | correct，completeness 12.50% | 100% | 答案收敛为“Cost-ops approves termination once the grace window expires.”，未再出现 5 business days/infra manager 的冲突断言。两裁判都认可核心批准人，但独立裁判认为覆盖事实较少。 |
| `qst_0416` | correct，completeness 83.33% | correct，completeness 83.33% | 75% | 60/140/260 QPS 与约 150 并发会话均保持，未见 guard 破坏答案。 |

冲突题汇总 correctness 两裁判均为 100%，但 completeness 为 DPV4 72.91%、Qwen/Lark 47.91%。这说明确定性约束主要发挥“删除冲突/不可信扩写”的安全作用，不会自动补足被删除或检索不到的字段；`qst_0413` 的主要收益来自生成阶段，而不是检索召回。

## 诊断结论

1. AB50 的 recall 从 70.39% 到 76.12%，但 O4.P3.4 约束本身不改变召回；召回增益应归因于其复用的 O4.P3 候选池/多视图配置，不能把它误记为冲突 guard 的检索收益。
2. `qst_0413` 在 recall=100% 时由冲突答案变为正确核心答案，确认该题的首要问题是生成阶段的作用域/批准人约束，而非 raw-miss。
3. DPV4 自评较宽松：其 correctness 比独立 Qwen/Lark 高 10 pp，且 5 个 disagreement 全部偏向 DPV4。后续放行不能只看 DPV4 自评，应至少同时看独立裁判和逐题事实审计。
4. 冲突 guard 仍应保持题型/意图限定，不能扩展为全局生成 guard；本轮冲突题与控制题未出现由 guard 导致的 correctness 回退。

## 放行建议

本轮不把确定性冲突约束作为全局 F500 默认开关。建议保留为 `conflicting_info` 及轻量冲突意图兜底分支的隔离策略，并在下一轮以独立裁判为主门槛，继续检查 completeness 是否因过度删除而下降。检索主线的下一优先级仍是 semantic/project 的 raw-miss 与候选覆盖，而不是继续扩大冲突题提示词。
