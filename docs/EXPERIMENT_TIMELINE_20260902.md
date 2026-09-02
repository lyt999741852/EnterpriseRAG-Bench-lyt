# 实验时间线与证据索引

更新时间：2026-09-02（Asia/Shanghai）  
用途：提供测试时间、优化路线和证据文件的统一索引；数值以链接的原始报告为准。

| 时间 | 阶段 / 实验 | 结论 | 主要证据 |
|---|---|---|---|
| 2026-07-30 | 早期 BGE Basic-50 | 仅 Basic 子集分数高，不代表全题型能力 | [有效汇总 §7](VALID_EXPERIMENT_TEST_SUMMARY_20260901.md) |
| 2026-08-14 | 冻结 F500 Qwen/Lark | 建立可回溯全量基线：combined 55.18 | [有效汇总 §3](VALID_EXPERIMENT_TEST_SUMMARY_20260901.md) |
| 2026-08-20～26 | PageIndex / conflict contract | 保留 PageIndex；修复 selector conflict 契约，Semantic30 有提升 | [A3.4 记录](SEMANTIC_A3_4_CONFLICT_CONTRACT_FULL_SMOKE_20260826.md) |
| 2026-08-27～28 | 召回、Conan 与 BGE 对照 | Conan 未证明替换价值；raw-miss 需分层定位 | [BGE/Conan 对照](CONAN448_DPV4_BGE50_20260828.md) |
| 2026-08-31 | F500 DPV4 与 O0–O4 漏斗 | F500 DPV4 参考线 combined 57.01；定位 raw-miss 与 evidence admission 两类问题 | [F500 记录](F500_BGE_DPV4_NO_CORRECTION_20260831.md)、[任务计划](F500_DPV4_OPTIMIZATION_TASK_PLAN_20260831.md) |
| 2026-09-01 | O3 索引/候选诊断 | 索引整体完整；扩大 pre-rerank 窗口有召回潜力，但不能直接扩大 rerank 输入 | [O3.8 记录](O3_8_TOPK_SWEEP_WIDE_RERANK_20260901.md) |
| 2026-09-02 | F500 O4.P3 | 全量 combined 58.88，较 DPV4 参考线 +1.87；额外文档上升，待复核 | [F500 O4.P3](F500_BGE_DPV4_O4P3_20260902.md) |
| 2026-09-02 | S3 AB150 | 无 PageIndex 固定混合策略暴露 Semantic 泛化不足，不合并为主线 | [S3 AB150](S3_AB150_TOP10_RESULTS_20260902.md) |

## 报告引用优先级

1. **系统总体能力**：F500 结果；优先引用最新、完整且同口径的结果。
2. **组件决策**：使用同题、单变量 A/B；例如 reranker、PageIndex、BGE/Conan。
3. **机理定位**：使用 smoke、逐层审计与离线 replay；不得宣传为端到端增益。
4. **候选方案**：明确写“待独立 judge / F500 放行”，不得用单次自评替代结论。

## 原始台账

- [有效实验测试汇总](VALID_EXPERIMENT_TEST_SUMMARY_20260901.md)：汇报级整合记录。
- [优化追溯原始台账](archive/ledgers/OPTIMIZATION_TRACE.md)：历史流水记录，供追溯，不是当前计划入口。
- [历史测试总记录（截至 2026-08-12）](archive/ledgers/RAG_TEST_RECORD_THROUGH_20260812.md)：早期记录。
