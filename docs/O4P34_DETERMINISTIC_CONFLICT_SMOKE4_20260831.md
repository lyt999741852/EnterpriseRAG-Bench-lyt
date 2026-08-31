# O4.P3.4：冲突题确定性事实约束与独立裁判复核

日期：2026-08-31
分支：`codex/semantic-a0`
运行目录：`/opt/enterprise-rag-bench/app/outputs/pageindex_o4p34_deterministic_conflict_smoke4_r1_20260831`

## 目的与隔离

本轮保持 O4.P3 的 BGE-small 只读索引、切块、BM25+dense+rerank、PageIndex、软池、DPV4 生成和 `no-correction` 口径不变，仅增加：

1. 对冲突题追加题型限定的 actor/scope/time-window guard；
2. 从问题文本提取显式时长，确定性删除答案中引入的不同 duration 句子；
3. 由于 question-only 路由将 `qst_0413` 误判为 constrained，增加基于“二选一 + approve/who”意图的非 gold 路由兜底，使上述规则真正覆盖冲突问题。

答案由 DPV4 生成，分别用 DPV4 和独立 Qwen/Lark（`http://10.72.100.35:7777/v1`）评分，均为 `--no-correction`。

## 结果

| 裁判 | correctness | completeness | combined | recall | invalid extra |
|---|---:|---:|---:|---:|---:|
| DPV4 | **100.00%** | 86.46% | 86.46 | 87.50% | 0.00 |
| Qwen/Lark 独立裁判 | **75.00%** | 73.96% | 48.96 | 87.50% | 0.00 |

逐题上，两个裁判都判 `qst_0413`、`qst_0386`、`qst_0416` 正确；Qwen 额外将控制题 `qst_0322` 判错，原因是答案加入了 gold 未列出的 “scheduler tweak”。

`qst_0413` 的最终答案被确定性约束收敛为：

> Cost-ops approves termination once the grace window expires.

它不再包含“5 business days/infra manager”冲突句；两个裁判均认可其核心批准人判断。该题仍只有 12.5% completeness，因为约束为安全删除，不会凭空补写 Miguel Reyes 等缺失事实。

## 诊断结论

- 这轮证明 O4.P3.2 的全局 guard 应限定到冲突意图；控制题不再因 guard 回退。
- 这轮也证明仅依赖 `question_type` 不可靠：严格 question-only 路由会把 `qst_0413` 判为 constrained，必须有轻量、非 gold 的冲突意图兜底。
- DPV4 与 Qwen 的 correctness 差异（100% vs 75%）确认了同一 LLM 自评偏高风险；后续放行应以独立裁判和事实约束共同通过为准。
- 本轮不是检索召回提升：4 题 recall 与前轮相同，收益来自生成后约束。

## 下一步

先将 `qst_0413` 类冲突约束扩展为可配置的字段级校验（批准人、明确时长、是否确认），并在冲突题 AB50 上同时跑 DPV4 与 Qwen 独立评分；只有独立裁判 correctness 不回退且控制题稳定，才考虑合入主链或申请 F500。
