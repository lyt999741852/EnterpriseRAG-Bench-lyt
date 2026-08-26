# AB50 检索层审计与候选池/分面 smoke（2026-08-26）

## 1. 冻结轨迹分层

对 `pageindex_ab50_semantic_conflict_guard_r3_20260826` 的已完成 route trace、answers 和官方 no-correction 结果做离线审计。有效题目分桶为：

| 首个失败层 | 题数 | 重点题目 |
|---|---:|---|
| raw miss | 5 | qst_0116、qst_0184、qst_0231、qst_0251、qst_0298 |
| RRF/rerank drop | 2 | qst_0050、qst_0093 |
| selector/PageIndex drop | 7 | qst_0041、qst_0197、qst_0241、qst_0280、qst_0390、qst_0413、qst_0447 |
| generation/coverage gap | 10 | 含 qst_0356、qst_0362 等目标文档部分命中题 |

`qst_0480` 为 high-level/InfoNotFound 类题，gold 没有 `expected_doc_ids`，不用于目标文档召回门禁。

## 2. Raw-miss bridge probe

对 5 道 raw miss 生成单条保守 bridge query，仅使用题干已有实体、事件和约束，不使用目标文档 ID 或答案。目标文档命中 **0/5**。因此不能证明简单查询改写能修复该组问题；后续应检查 embedding/index 覆盖或词法实体分解，不直接把 bridge query 接入主链。

## 3. 候选池扩大 smoke

变量：reranker `candidate_k` 从 120 提升到 180；其余配置、索引和 PageIndex cache 不变。12 题子集官方 no-correction：

| 指标 | 冻结基线子集 | candidate_k=180 | 变化 |
|---|---:|---:|---:|
| correctness | 25.00% | **41.67%** | +16.67 pp |
| completeness | 38.68% | **45.62%** | +6.94 pp |
| combined | 25.00 | **40.28** | +15.28 |
| document recall | 28.01% | **42.59%** | +14.58 pp |
| invalid extra | 0.42 | 0.25 | 仅诊断 |

目标文档存活情况显示：`qst_0050`、`qst_0093` 从 rerank 前丢失恢复到 rerank 后；其中 `qst_0093` 最终答对。`qst_0231` 仍未进入 rerank，说明单纯 120→180 仍不够。`qst_0356` 出现完整度回退，故该变量暂不进入 AB50。

## 4. 通用分面配额 smoke

变量：启用 `semantic_evidence_quota`，对 semantic/project_related/completeness 题最多 3 个独立分面查询，每个分面保留 3 个 reranked chunks；不锁定题目或目标文档。8 题官方 no-correction：

| 指标 | 冻结基线子集 | facet quota | 变化 |
|---|---:|---:|---:|
| correctness | 37.50% | 50.00% | +12.50 pp |
| completeness | 47.60% | 58.01% | +10.42 pp |
| combined | 37.50 | 47.92 | +10.42 |
| document recall | 42.01% | 54.51% | +12.50 pp |
| invalid extra | 0.25 | 0.25 | 不变 |

但提升主要来自 `qst_0272` 的既有 conflict-contract selector 恢复；`qst_0197`、`qst_0447`、`qst_0356`、`qst_0362` 的检索/覆盖瓶颈没有解除，因此不视为通过的检索方案。

## 5. 门禁与下一步

- 本轮不运行 AB50：候选池扩大有信号但存在 qst_0356 回退，分面配额未改变关键多文档题。
- 下一候选变量应是“候选池扩大 + rerank 后按分面/文档保留”的组合，但必须先做 6～8 题单变量 smoke，确认不牺牲已有正确题。
- raw miss 组转向词法实体/版本/数字锚点和 embedding 覆盖诊断；bridge query 0/5 不放行主链。
- F500 仍保持停止，直到检索变量在小样本达到 correctness 提升且无明显回退。
