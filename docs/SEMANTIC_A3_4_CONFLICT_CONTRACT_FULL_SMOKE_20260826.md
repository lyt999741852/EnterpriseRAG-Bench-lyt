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
- 配置未启用官方评测，因此尚不能宣称 500 题官方分数提升。

## 结论

conflict contract 在固定 Semantic30 上通过了诊断级整体 smoke：目标 selector 题净增加 2 题召回，且未出现明显答案污染。根据打榜口径，无效额外文档不再作为独立阻断条件；下一步应进行官方 no-correction 评分，再决定是否接回 PageIndex ON 的 AB50 回归。若官方分数无增益，则停止 A3 合流，转向 raw miss/RRF 检索优化。
