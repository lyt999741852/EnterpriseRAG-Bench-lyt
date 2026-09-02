# BGE 50 题 DPV4 LLM 单变量实验

日期：2026-08-28  
实验输出：`outputs/pageindex_balanced50_bge_rerank_question_only_llm_route_multiview_dpv4_20260828`

## 目的

在已冻结的 BGE-small + remote rerank 50 题链路上，仅将 Qwen/Lark
替换为 DeepSeek-V4-Flash，评估 LLM 替换对端到端质量的影响。Conan 数据集、
切块、Embedding、Elasticsearch 索引、候选池、rerank、PageIndex、证据选择和题集均未改变。

500 题冻结基线：

- 配置：`configs/snapshots/eval_pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817.yaml`
- SHA-256：`25e4f322178ff41fab82f87083e6c143f5e1dc9f230836a79d719674430d941c`
- no-correction：correctness 60.6%、completeness 62.57%、combined 55.18、recall 61.12%

50 题原 Qwen 基线：

- 配置：`configs/eval_pageindex_balanced50_bge_rerank_question_only_llm_route_multiview_20260814.yaml`
- correctness 64%、completeness 65.49%、combined 59.14、recall 60.87%、invalid extra docs 0.23

## DPV4 配置

配置文件：`configs/eval_pageindex_balanced50_bge_rerank_question_only_llm_route_multiview_dpv4_20260828.yaml`

只替换以下 LLM 字段：

```yaml
api_base: "http://10.72.100.29:18380/v1"
api_key_env: "DPV4_API_KEY"
model_name: "deepseek-v4-flash"
```

`temperature: 0`、`max_tokens: 8192`、并发 4 和原 50 题基线保持一致。密钥仅通过远端环境变量注入。

## 最终评分（官方 no-correction）

| 指标 | Qwen/BGE 基线 | DPV4/BGE | 变化 |
|---|---:|---:|---:|
| correctness | 64.00% | **68.00%** | **+4.00 pp** |
| completeness | 65.49% | **71.37%** | **+5.88 pp** |
| combined | 59.14 | **62.13** | **+2.99** |
| document recall | 60.87% | **70.39%** | **+9.52 pp** |
| invalid extra docs | 0.23 | **0.17** | -0.06 |

DPV4 共完成 50/50 题；答案校验通过。Pipeline 简单指标为 recall 70.4%、invalid extra docs 0.2。

## 分类型变化

| 类型 | correctness | completeness | recall |
|---|---:|---:|---:|
| basic (18) | 77.78 → 72.22 | 76.57 → 80.19 | 72.22 → 72.22 |
| semantic (12) | 33.33 → **58.33** | 37.50 → **64.05** | 33.33 → **66.67** |
| intra-document reasoning (4) | 100 → 75 | 100 → 87.50 | 100 → 100 |
| project-related (4) | 50 → 50 | 64.91 → 56.95 | 56.95 → 39.58 |
| constrained (3) | 66.67 → **100** | 79.49 → **90.11** | 66.67 → **100** |
| conflicting info (2) | 50 → **100** | 60.41 → 54.16 | 25 → **75** |

逐题 correctness：5 题由错变对，3 题由对变错，42 题不变，净增 2 题（32 → 34）。

## 解释与限制

虽然实验只替换了 LLM 配置，但当前链路中的 LLM 同时参与 query rewrite、answer-intent、
question router 和最终答案生成。因此 recall 从 60.87% 提升到 70.39%，尤其 semantic
题召回提升，说明 DPV4 的改写/意图查询也改变了候选集合；这不是“固定检索候选后只比较
最终生成器”的纯生成 A/B。

此外，官方 no-correction 评分器本身也通过 `LLM_API_BASE`、`LLM_API_KEY` 和
`LLM_MODEL_NAME` 调用 LLM judge。本次 DPV4 结果使用 DPV4 作为 judge，而原 Qwen
基线结果使用 Qwen 作为 judge，所以 correctness/completeness 的绝对差异包含
“生成模型变化 + judge 模型变化”两个因素。要把生成收益单独归因，需要用同一个
固定 judge 重新评分两套答案。

交叉评分已于 2026-08-28 完成：

| 生成器 | Judge | correctness | completeness | combined | recall |
|---|---|---:|---:|---:|---:|
| Qwen | Qwen | 64.00% | 65.49% | 59.14 | 60.87% |
| Qwen | DPV4 | **70.00%** | **73.60%** | **68.09** | 60.87% |
| DPV4 | Qwen | 58.97% | 63.00% | 51.41 | 70.73% |
| DPV4 | DPV4 | 68.00% | 71.37% | 62.13 | 70.39% |

因此，DPV4 judge 对 Qwen 答案的分数高于对 DPV4 自身答案的分数，没有观察到
“DPV4 自评必然偏高”。但两个 judge 的评分尺度不同：在 Qwen 答案上 DPV4 judge
比 Qwen judge 高 6.00 个 correctness 点，在 DPV4 答案上高 9.03 个点。固定同一
judge 后，Qwen 答案的 correctness/completeness 仍略高于 DPV4，DPV4 的明确优势
主要体现在 document recall，而不是当前这组交叉评分下的最终回答分数。

代表性变化：`qst_0272`、`qst_0280`、`qst_0390`、`qst_0413` 由原先无证据拒答恢复为有证据回答；
`qst_0322` 在相同目标文档下遗漏配置开关，`qst_0432` 则因候选召回变化而退化。

## 后续建议

1. 暂不切换 Conan；先把本结果作为 DPV4+BGE 50 题基线。
2. 若需要分离“检索改写收益”和“生成收益”，冻结原 Qwen 的 route/rewrite/answer-intent
   轨迹，再只用 DPV4 重生成答案。
3. 若确认端到端提升稳定，再在相同 DPV4 配置下切换 Conan 1792 维索引，单独评估数据集/切块变量。
