# S4 全量 500 题结果

日期：2026-09-03  
链路：无 PageIndex；固定四路 hybrid Top-500；RRF fail-open；文档级 admission；DPV4；`--no-correction`。

## 总体评分

| 版本 | 正确性 | 完整性 | 综合分 | 文档召回 | 无效额外文档 |
|---|---:|---:|---:|---:|---:|
| S3 冻结基线 | 71.40 | 74.69 | 66.07 | 69.07 | 0.54 |
| S4 本轮 | 68.40 | 69.01 | 62.69 | 63.58 | 0.58 |
| S4 - S3 | -3.00 | -5.68 | -3.38 | -5.49 | +0.04 |

## 检索与生成诊断

- S4 pre-rerank Recall@500：86.40%，比 S3 四路候选池的 83.40% 高 3.00 个百分点。
- 但 admission 后候选命中率降至 77.00%，生成后的文档召回为 63.58%；扩大候选没有转化成有效答案证据。
- Semantic pre-rerank @500 为 76.00%，生成评分正确性 48.00%；Project Related 正确性 62.50%；Completeness 正确性 70.00%。
- 本轮 rerank 推理接口不可用，使用 RRF 顺序 fail-open；因此不能把结果解释为“rerank 优化失败”，主要结论是文档级保留和生成阶段仍有证据损失。

## 产物

远端：`/opt/enterprise-rag-bench/app/outputs/s4_full500_docaware_union_20260903/`  
本地：`outputs/s4_full500_docaware_union_20260903/`

包含 `retrieval_report.json`、`generation_report.json`、`answers.jsonl` 和 `official_score/results.json`。

