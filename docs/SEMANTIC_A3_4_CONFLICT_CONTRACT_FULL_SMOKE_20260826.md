# Semantic A3.4 conflict contract Semantic30 重跑

日期：2026-08-26（Asia/Shanghai）
范围：固定 Semantic30、PageIndex OFF；仅启用 precision-v3 conflict reporting contract。

## 运行与隔离

- 独立配置：`semantic_a34_rerun2_semantic30_conflict_contract_20260826`。
- 远端输出：`outputs/semantic_a34_rerun2_semantic30_conflict_contract_20260826/`。
- 使用环境变量提供 LLM 与 reranker 凭据；不写入配置文件。
- Elasticsearch 只读复用既有 BGE 索引；未重建索引、manifest 或冻结 S1 输出。
- runtime prompt 补丁仅在运行期间存在，完成后已回滚并通过 `py_compile` 核验。

## 结果

| 指标 | S1 基线 | A3.4 重跑 | 变化 |
|---|---:|---:|---:|
| 简单目标文档召回 | 53.3%（16/30） | **60.0%（18/30）** | **+6.7 pp** |
| 平均无效额外文档 | 0.53 | 0.50 | 仅作诊断 |

- `qst_0176`、`qst_0272` 两个已确认 selector drop 均恢复。
- `qst_0208` 本轮恢复目标文档及正确答案，未复现此前单次全量运行的退化。
- raw miss 与 RRF/rerank drop 仍然存在；本实验不改变检索阶段。
- 随后使用同一份 answers 运行官方 no-correction 评分：correctness **56.67%**、completeness **60.21%**、combined **52.22**、recall **60.0%**。
- 该 52.22 是 Semantic30 诊断子集分数，不等同于 500 题基线 55.18，不能直接宣称 500 题分数提升。

## 结论

conflict contract 在固定 Semantic30 上通过了诊断级整体 smoke：官方 combined 由 S1 的 **45.56** 提升至 **52.22（+6.66）**，全部净提升来自 `qst_0176`、`qst_0272` 两个 selector drop 的证据恢复。根据打榜口径，无效额外文档不作为独立阻断条件；下一步接回 PageIndex ON 做 AB50 回归，再决定是否进入 500 题评测。该改动只反馈 evidence selector/admission 层，不解决 raw miss、RRF/rerank 或泛化 generation 问题。
