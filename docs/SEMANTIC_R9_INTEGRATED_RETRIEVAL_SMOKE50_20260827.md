# R9 集成检索回归（AB50）

日期：2026-08-27
基线：`pageindex_ab50_semantic_conflict_guard_r3_20260826`（A4/B4）
实验：`pageindex_r9_integrated_retrieval_smoke50_20260827`

## 目的与变量

R9 将三个系统级变量放入同一次 AB50 回归：

1. 为 question-only 的 `unknown` 路由复制 Semantic 多视图（原题 keyword/dense、rewrite dense、answer-intent dense）。
2. 对 semantic、unknown、project_related、completeness 保留最多 3 个分面查询、每查询最多 2 个候选。
3. 在所有检索分支合并后增加全局候选上限：每文档最多 2 个 chunk、总计最多 30 个 chunk。

实验使用固定 AB50 题目、`question_only=true`、无目标文档锁定；远端全局上限通过临时补丁注入，运行结束已回滚并通过 `py_compile`。

## 官方 no-correction 结果

| 指标 | A4/B4 基线 | R9 | 变化 |
|---|---:|---:|---:|
| Correctness | 64.00% | 64.00% | +0.00pp |
| Completeness | 66.50% | 64.46% | -2.04pp |
| Combined | 59.41 | 58.57 | -0.84 |
| Document recall | 63.89% | 61.05% | -2.84pp |
| Invalid extra docs | 0.19 | 0.17 | -0.02 |

50/50 题完成，评分器 `skipped_rows=0`。首次 0 分评分是远端评分进程未透传 LLM 环境变量，已用显式 `LLM_PROVIDER=openai`、`LLM_API_KEY`、`LLM_API_BASE`、`LLM_MODEL_NAME` 重跑；上表为修正版结果。

## 题型对比

| 题型 | 基线 Combined / Recall | R9 Combined / Recall | 结论 |
|---|---:|---:|---|
| semantic（12） | 31.94 / 41.67% | 31.94 / 33.33% | correctness 不变，召回下降 |
| project_related（4） | 44.72 / 50.70% | 39.17 / 42.36% | 下降 |
| completeness（2） | 0.00 / 25.00% | 0.00 / 25.00% | 无改善 |
| basic（18） | 73.61 / 77.78% | 72.50 / 77.78% | 完整性轻微下降 |

R9 的收益仅体现在个别生成随机性：`qst_0298` correctness 由 false 变 true；但这不是检索覆盖提升（提交文档仍为同一文档），不足以抵消整体回退。

## 关键逐题证据

- `qst_0231`：unknown 变量确实生效，trace 出现 rewrite/answer-intent 查询；共享候选文档仍未进入最终选中文档，答案改为泛化的 90 天/S3-SFTP 结论，仍不能证明题干限定的 healthcare 合同场景。
- `qst_0272`（控制题）：原本 basic/es-only，R9 trace 仍注入 semantic rescue，最终答案文档集合变为空；官方结果由正确、100% recall 回退为错误、0% recall。说明当前 rescue/quota 作用域没有严格绑定题型，破坏了控制路由。
- `qst_0350`：提交文档从 2 个缩为 1 个，recall 66.67%→33.33%，completeness 88.89%→66.67%。全局每文档/总量上限在多跳题上误删了第二个必要证据。
- `qst_0432`：提交文档从 4 个缩为 3 个，但官方 correctness 未变化；证明 extra 文档下降不等于证据质量提升。

## 配额审计

50 条 route trace 全部满足上限：最终全局候选为 29–30 chunks、23–30 个文档，每文档最多 2 chunks，未发现约束违规。问题在于“先合并再硬截断”的位置：它没有按分面或必需证据保留，可能截掉多跳题的第二个文档；同时 semantic rescue 在 basic 控制题上仍被触发。

## 结论与后续

R9 **不通过，不合流，不运行 F500**。本实验回答了系统级方向：单纯扩大 unknown 多视图、统一分面配额和全局 chunk cap 不能解决当前 64% correctness 瓶颈，且会造成多跳/控制题回退。

下一步转向更大粒度、可验证的检索改造：

1. 先修复路由作用域：semantic rescue/quota 只对明确允许的题型生效，basic 控制题保持原 ES-only 路径。
2. 将“全局硬截断”改为分面/文档感知的保留策略：先保证每个必需分面至少一个候选，再应用软上限；不再以固定顺序删除证据。
3. 对 raw-miss 继续做索引覆盖/表征层改造（混合 lexical、实体/数字锚点及可解释的 query expansion），而不是继续叠加更多题目级 selector 规则。
4. 上述变量先做 10–12 题系统级 smoke，只有 correctness、recall、控制题均不回退时才重新跑 AB50；F500 继续冻结。
