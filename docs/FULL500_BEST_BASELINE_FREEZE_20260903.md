# 全量 500 题最佳基线冻结

冻结日期：2026-09-03  
基线名称：S3 无 PageIndex、四路混合检索 + 一轮覆盖反思 + Top-10 admission

## 结果指纹

| 指标 | 基线结果 |
|---|---:|
| 正确性 | 71.40 |
| 完整性 | 74.69 |
| 综合分 | 66.07 |
| 文档召回 | 69.07 |
| 无效额外文档 | 0.54 |
| 题数 / 跳过 | 500 / 0 |

该结果是目前已完成全量测试中综合分和正确性最高的一版；评分使用官方
`metrics_based_eval --no-correction`，但 judge 为 DPV4，属于内部可比结果，
不是官方 GPT judge 榜单值。

## 可复现框架

- 数据：官方 `questions.jsonl`，题号清单
  `configs/s3_full500_question_ids_20260902.txt`。
- 索引：Elasticsearch `enterprise-rag-bge-small-v1`（alias
  `enterprise-rag-bge-small`），BGE-small-en-v1.5，384 维，CPU，离线加载。
- 召回：不做题型路由；原题、词法、语义、facet 四路视图，RRF 合并，候选池
  Top-240，固定 rerank 后候选。
- 反思：DPV4 覆盖检查最多 1 轮；线上不读取
  `expected_doc_ids`、gold answer 或 answer facts。
- 生成：DPV4 `deepseek-v4-flash`，temperature 0，`no-correction`，Top-10
  文档 admission；PageIndex 关闭。
- 入口脚本：
  `scripts/diag/run_s3_no_pageindex_agentic_20260902.py`、
  `scripts/remote/run_s3_full500_top10_20260902.sh`。

## 已保存产物

本地独立副本：`outputs/baseline_s3_full500_top10_20260903/`

- `answers.jsonl`
- `retrieval_report.json`
- `official_score/results.json`
- `official_score/score.log`
- `run.log`

SHA-256（用于防止误覆盖）：

```text
answers.jsonl       47282337E180B0E0084DC638B0D0631FC75813AACC8266287EECECD8E6F42591
retrieval_report    0D843ADE43D4B5D06092AF869A1C756FDAE8803D35C2425DD7F87A788B2F38BB
official results    20D4D50CEC65D5F3D5420818301A18E9303C9B20898B33E78E6E77FA72232C8E
```

远端原始目录：`/opt/enterprise-rag-bench/app/outputs/s3_20260902/full500_top10/`。
后续实验不得写入该目录；新实验使用独立版本目录并保留本文件和上述产物。
