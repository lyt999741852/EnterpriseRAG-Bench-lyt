# S3 主架构冻结

冻结日期：2026-09-08

## 主架构

- 入口：`scripts/diag/run_s3_no_pageindex_agentic_20260902.py`
- 全量启动：`scripts/remote/run_s3_full500_repro_20260903.sh`
- 题集：`questions.jsonl`，500/500，题号清单 `configs/s3_full500_question_ids_20260902.txt`
- 检索：BGE-small + BM25/dense hybrid，原题/词法/语义/facet 四路 RRF
- 后处理：remote rerank，一轮缺口反思检索，Top-10 evidence admission
- 生成：DPV4 `deepseek-v4-flash`，temperature 0
- PageIndex：关闭
- benchmark metadata：`question_type=None` 进入生成器；gold 文档和答案只用于离线诊断/评分
- Git commit：`81c456f5c74000e740c19f8c5ccd8d1537b83371`

## 冻结结果

运行目录：`outputs/s3_repro_full500_20260903/`

| 指标 | no-correction |
|---|---:|
| 正确性 | 72.60 |
| 完整性 | 75.08 |
| 综合分 | 67.01 |
| 文档召回 | 69.39 |
| 无效额外文档 | 0.49 |

固定输入指纹：

```text
answers.jsonl       37e042fa7c941c6a2666e42330f41f688282fe05812eae713c954f6350a3a08a
retrieval_report    2eb9fceefdb854632e1ab29038aade6a1a6e5bb9e3e83235c0e2d4f98794efc1
no-correction score e7c9f5fdf091fb96a76d44dd2f1c685d87f7739e229aebfe5cc77a27a9b41e43
```

Correction 必须复用上述 `answers.jsonl`，写入独立的
`official_correction_dpv4_20260908/`，不得修改或覆盖原答案和 no-correction 结果。

## Correction 双裁判复核

两轮均复用同一份冻结的 `answers.jsonl`，不重新执行检索或答案生成。官方
correction 文档 bundle 共包含 1001 份去重文档；DPV4 与 Qwen 的评分输出使用
独立目录，未覆盖冻结产物。

| 裁判 | 正确性 | 完整性 | 综合分 | 文档召回 | 无效额外文档 | 修正题数 |
|---|---:|---:|---:|---:|---:|---:|
| DPV4 | 72.80 | 74.90 | 67.15 | 69.95 | 0.48 | 9 |
| Qwen3.5-27B (`lark`) | 63.80 | 66.77 | 55.73 | 69.45 | 0.48 | 2 |

DPV4 与 Qwen 对同一批 DPV4 答案的综合分相差 11.42。该差值说明内部成绩对
裁判模型高度敏感，DPV4 自评存在潜在偏高风险；但 correction 本身也由裁判
参与，两轮分别修正 9 题和 2 题，因此不能把全部差值直接解释为自评偏差。
后续架构对比应冻结同一份 corrected questions，再分别运行 judge-only 评分。

本轮输出：

- `outputs/s3_repro_full500_20260903/official_correction_dpv4_20260908/`
- `outputs/s3_repro_full500_20260903/official_correction_qwen_20260908/`
