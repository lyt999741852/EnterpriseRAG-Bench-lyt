# R8 低权重实体对候选最小 Smoke（2026-08-27）

## 目的与隔离变量

本次只验证一条候选生成变量：从题干提取实体/数字/专名，生成最多 20 个实体对 BM25 查询；每个查询的候选按文档最多保留 2 个 chunk，候选权重为 0.2。配置基于 `eval_pageindex_ab50_semantic_conflict_guard_r3_20260826.yaml`，固定 8 题（5 个 raw-miss/目标题，4 个控制题中与本轮集合重叠的 4 题），不写入 ES，不改变 BGE 索引。

实现通过远端临时 patch 注入，测评结束后已回滚并完成 `python -m py_compile src/pipeline.py`；`pipeline.py` 与备份文件均恢复干净。实验配置为 `configs/eval_pageindex_lexical_anchor_smoke8_20260827.yaml`。

## 官方 no-correction 结果

使用正确的 LLM 环境变量（`LLM_API_KEY`、`LLM_API_BASE`、`LLM_MODEL_NAME`）评分，结果文件为 `outputs/pageindex_lexical_anchor_smoke8_20260827/results_api2.json`：

| 指标 | R8（8 题） |
|---|---:|
| correctness | 12.50%（1/8） |
| completeness | 31.25% |
| combined | 12.50 |
| document recall | 15.62% |
| invalid extra docs | 0.38 |

逐题 correctness：`qst_0272` 为 true，其余 7 题为 false。`qst_0272` 的 recall/completeness 均为 100%。

## 控制题无回退门禁

对照采用上一轮 candidate-pool smoke 的同题结果（`outputs/pageindex_retrieval_pool_smoke12_20260826/results.json`）：

| 控制题 | 对照 correctness | R8 correctness | R8 recall | 结论 |
|---|---:|---:|---:|---|
| `qst_0093` | true | false | 0% | 回退 |
| `qst_0211` | true | false | 0% | 回退 |
| `qst_0272` | true | true | 100% | 保持 |
| `qst_0356` | false | false | 25% | 无新增回退 |

因此“控制题无回退”未通过，R8 不得合流或用于 AB50/F500。

## 证据审计

- `qst_0093` 进入了组合分支并生成 20 个 pair view（8 个题干 token，20 个组合）；但 rerank 输入仍固定为 120、输出 30，最终 PageIndex scoped 结果仅 3 个 chunk/1 个文档，gold 文档不在最终集合。低权重并没有阻止大量 pair view 挤占候选池。
- `qst_0231` 在本次 question-only 路由中被标记为 `unknown`，而配置只对 `semantic` 开启组合候选，因此没有产生 `semantic_anchor_rescue`；上一轮发现的 `patient+connector` 恢复路径没有被本 smoke 覆盖。
- 全部 8 题最终生成集合的每文档 chunk 数最大为 2（`qst_0356`），说明局部 per-query 限制生效；但它没有限制跨 pair 的全局候选膨胀。
- qst0093/qst0211 的回退表明，当前“多 pair view + 低权重”插入位置仍会改变 rerank/selector 输入，不能作为无副作用补召回层。

## 结论与后续

R8 失败：实体对确实能进入检索视图，但当前实现既未覆盖 `unknown` raw-miss，也未控制跨 pair 的全局候选规模，并导致 2/4 控制题回退。保留诊断产物，不接入主链；下一步应先做更小的只读诊断：仅对 `unknown` raw-miss 启用已验证的实体对，并增加全局候选/文档配额或只在基线无目标文档时触发，然后重新通过同一组控制题门禁。
