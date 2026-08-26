# Semantic A3.A selector / generation 逐题离线证据审计

## 结论

对 Semantic30 S1 中 A0 标记的 2 个 `selector_drop` 和 4 个 `generation_gap` 完成逐题离线审计：

- 2 个 selector drop 均为真实的证据选择误拒。目标文档已位于生成前最终证据第 1 位，最终 chunk 明确包含题目所需事实，但提交答案选择了空文档并 fail-closed。
- 4 个 generation gap 中没有可直接用于生成提示优化的干净样本：1 题的最终目标 chunk 缺少所需关键事实且混入 3 个无效文档；其余 3 题答案已覆盖题目明确询问的事实，官方正确性判定也确认核心事实正确，但 completeness 仍被扣分。
- 因此 A3.A 只放行 2 题的 selector 离线复放诊断；不放行 generation prompt 改动，也不启动在线评测。

## 审计边界

- 冻结运行：`outputs/semantic30_r4_s1_lexical_anchor_20260820`。
- 仅在评测完成后读取 gold document ID、answer facts、官方评分和 trace。
- 通过最终 chunk ID 对 ES 做精确 `_mget`，不执行检索、不写索引、不调用生成模型。
- 原始审计 JSON 保留在运行输出目录，不纳入 Git。

## 逐题证据

| 题目 | A0 分层 | 逐阶段证据 | 答案/评分表现 | A3.A 归因与处置 |
|---|---|---|---|---|
| `qst_0176` | selector drop | 目标文档 keyword 第 2、dense 第 10、rerank 前第 2、rerank 后第 1、final 第 1；最终 chunk 明确给出 H200 80GB、`eu-central-1`、`ap-south-1` 及 `2026-04-06 09:00 UTC`。 | submitted documents 为空，答案以“证据不足”拒答。 | **selector 真实误拒**；进入 A3.P 离线 selector 复放。 |
| `qst_0272` | selector drop | 目标文档 keyword 第 25、rerank 前第 35、rerank 后第 1、final 第 1；最终 chunk 明确写有 routine approvals 的目标 SLA 为 **72 business hours**。 | submitted documents 为空，答案以“证据不足”拒答。 | **selector 真实误拒**；进入 A3.P 离线 selector 复放。 |
| `qst_0189` | generation gap | 目标文档 keyword 第 3、dense 第 66、rerank 前第 20、rerank 后/final 第 21；提交目标文档同时混入 3 个无效文档。最终目标 chunk 不含预期的 `--enforce-origin-verification`，也不含 origin verification/hard failure 对应说明。 | 答案生成了不受证据支持的 `--require-anchor`。 | **final chunk 覆盖缺口 + 额外文档污染**；不属于纯生成问题，排除 generation prompt 优化。 |
| `qst_0200` | generation gap | 目标文档进入 final 并被提交。 | 答案准确给出 200 tokens 时响应时间目标 `<=18s`；correct=true、completeness=50。官方 reasoning 明确确认回答匹配题目要求的核心事实。 | **评分完整性不一致**；隐藏 facts 中的 peak concurrency 不是题目所问，不应为刷分强加到答案。排除在线改动。 |
| `qst_0208` | generation gap | 目标文档 final/submitted 均第 1。 | 答案给出 1800 rps、3 倍 600 rps baseline、60 秒窗口；correct=true、completeness=50。官方 reasoning 确认所有关键数值与核心问题均匹配。 | **评分完整性不一致**；排除在线改动。 |
| `qst_0232` | generation gap | 目标文档 final/submitted 均第 1。 | 答案包含 proposal 标题、确定性 merge 策略（含 `merge_patch`）以及 RetryPolicy 的指数退避、jitter、`retry_budget_ms`；correct=true、completeness=66.67。官方 reasoning 确认标题和策略描述正确。 | **评分完整性不一致**；排除在线改动。 |

## 可执行判断

本轮将 A0 的粗粒度 `generation_gap` 进一步拆开后，得到：

- `submitted_evidence_drop`：2 题；均具备精确事实证据，可进入 selector 专项诊断。
- `generation_with_extra_documents`：1 题；最终 chunk 本身缺事实，不能用生成提示修补。
- `correct_answer_low_completeness`：3 题；属于答案正确与 completeness 扣分并存的评估不一致候选。
- 干净的 `answer_synthesis_gap`：0 题。

## 下一任务：A3.P

A3.P 仅对 `qst_0176`、`qst_0272` 做 selector 的离线复放与输入输出审计：

1. 从冻结 trace 和最终 chunk 构造与线上一致的 selector 输入，不读取 gold facts 生成提示。
2. 记录 selector 原始响应、解析结果、拒绝原因和稳定性；不接入 pipeline，不运行答案生成。
3. 只有在相同问题与证据下可重复误拒，且能定位为 selector 规则/解析问题时，才提出单变量 A3 smoke；否则停止 A3。

## 验证

- `python -m py_compile scripts/diag/audit_semantic_selector_generation.py`
- 冻结 S1 产物共输出 6 条唯一记录，分层计数为 2 / 1 / 3，且逐题均取得完整 question、answer、trace、score。
- `git diff --check`
