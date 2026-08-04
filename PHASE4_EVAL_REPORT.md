# 阶段四：10 题与 50 题评测报告

完成时间：2026-07-29（Asia/Shanghai）  
检索索引：`enterprise-rag-bge-small-v1`（928,534 chunks）  
嵌入模型：`BAAI/bge-small-en-v1.5`  
生成/评分模型：内网 Qwen `lark`

## 结果

| 指标 | 10 题 | 50 题 |
| --- | ---: | ---: |
| 完成题数 | 10/10 | 50/50 |
| 答案结构校验 | 通过 | 通过 |
| 空答案 / LLM 错误 | 0 / 0 | 0 / 0 |
| 答案正确性 | 60.0% | 66.0% |
| 答案完整性 | 71.0% | 76.32% |
| 正确性×完整性综合分 | 56.0 | 64.2 |
| 文档召回率 | 80.0% | 86.0% |
| 平均无效额外文档 | 6.6 | 6.74 |
| 跳过题数 | 0 | 0 |
| 金标准修正题数 | 0 | 0 |

10 题运行与 50 题运行的前 10 个答案逐字一致，证明两级门禁使用了同一推理条件，结果可直接比较。

## 50 题召回明细

50 个问题中 43 个命中金标准文档，7 个未命中：

```text
qst_0002
qst_0004
qst_0016
qst_0039
qst_0041
qst_0043
qst_0050
```

| 来源 | 题数 | 平均召回率 |
| --- | ---: | ---: |
| confluence | 10 | 90.0% |
| fireflies | 5 | 60.0% |
| github | 4 | 75.0% |
| gmail | 7 | 100.0% |
| google_drive | 6 | 66.7% |
| hubspot | 3 | 100.0% |
| jira | 6 | 100.0% |
| linear | 7 | 100.0% |
| slack | 2 | 50.0% |

来源样本量较小，尤其 Slack 只有 2 题，因此该表只用于定位优化方向，不能作为来源级最终结论。

## 评测方法

- 问题按 `question_id` 稳定排序：10 题为 `qst_0001`–`qst_0010`，50 题为 `qst_0001`–`qst_0050`。
- 两组均为 `basic` 类型；尚未覆盖完整 500 题中的语义、跨文档、冲突信息、完整性和未找到信息等类型。
- 检索采用混合召回：BM25 + BGE dense KNN + weighted RRF，`top_k=10`、`candidate_k=100`、`dense_weight=0.3`。
- 官方 `metrics_based_eval` 使用 `--no-correction`，不会改写金标准答案、事实或预期文档。
- 官方评测源码锁定到 `onyx-dot-app/EnterpriseRAG-Bench` commit `d36685e273713975ee20299bbf1ab64165575b3c`。
- 上游默认 OpenAI Responses API；为了接入内网 Qwen，仅将 `src/llm/openai_llm.py` 的传输层适配为 Chat Completions。评分提示词、事实核验、正确性判断和统计公式未修改。
- 生成模型与评分模型均为同一 Qwen `lark`，适合作为当前内部质量门禁，但存在同模型自评偏差，不应直接等同于使用独立裁判模型的公开排行榜分数。

## 发现的问题

1. 50 题召回率 86%，较历史不可信的 16.1% 已显著提高，但仍有 7 个明确漏召回题。
2. 平均无效额外文档约 6.74，说明当前返回的证据文档集合偏宽；这会增加上下文噪声，并直接拉低官方文档精度相关表现。
3. 部分题即使召回正确文档仍被判答案错误，例如 `qst_0001` 同时输出互相冲突的限制值；需要改善证据聚合和冲突抑制，而不只是提高召回。
4. Fireflies、Google Drive、GitHub 和 Slack 是本批次优先排查来源，但需要在更大且分层的样本上确认。

## 产物

```text
outputs/eval_10_es_qwen_20260729/answers.jsonl
outputs/eval_10_es_qwen_20260729/results.json
outputs/eval_10_es_qwen_20260729/simple_metrics.json
outputs/eval_10_es_qwen_20260729/validation.json
outputs/eval_50_es_qwen_20260729/answers.jsonl
outputs/eval_50_es_qwen_20260729/results.json
outputs/eval_50_es_qwen_20260729/simple_metrics.json
outputs/eval_50_es_qwen_20260729/validation.json
```

关键文件已从服务器同步回本地并核对 SHA-256，与服务器完全一致。

## 下一步建议

正式 500 题前先针对 7 个漏召回题做查询、BM25、dense 和 hybrid 排名诊断；再测试减少候选文档噪声的方案，例如文档级去重、动态证据数、轻量 reranker 或仅提交实际使用的引用文档。优化后应重新运行相同 50 题门禁，要求不降低 86% 召回率，同时显著降低平均额外文档并提升综合分。
