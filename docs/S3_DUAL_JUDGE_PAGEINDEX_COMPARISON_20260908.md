# S3 双裁判与 PageIndex 全量结果对比

日期：2026-09-08

## 结果

| 架构 | 生成 | 裁判 | 口径 | 正确性 | 完整性 | 综合分 | 文档召回 | 无效额外文档 |
|---|---|---|---|---:|---:|---:|---:|---:|
| O4.P3 PageIndex | DPV4 | DPV4 | no-correction | 64.00 | 67.63 | 58.88 | 64.49 | 0.34 |
| S3 无 PageIndex | DPV4 | DPV4 | no-correction | 72.60 | 75.08 | 67.01 | 69.39 | 0.49 |
| S3 无 PageIndex | DPV4 | DPV4 | correction | 72.80 | 74.90 | 67.15 | 69.95 | 0.48 |
| S3 无 PageIndex | DPV4 | Qwen3.5-27B | correction | 63.80 | 66.77 | 55.73 | 69.45 | 0.48 |

## 可比较结论

O4.P3 与 S3 的 DPV4 no-correction 行是当前唯一同生成、同裁判、同评分口径的
架构对照。S3 相对 O4.P3 的正确性提高 8.60 个百分点、完整性提高 7.45 个
百分点、综合分提高 8.13、文档召回提高 4.90 个百分点，代价是平均无效额外
文档增加 0.15。S3 的 correction 相对 no-correction 仅提高 0.14 综合分，说明
其主要提升不是 correction 所致。

Qwen 对同一份 S3 答案给出的综合分比 DPV4 低 11.42，表明裁判尺度是当前结果
中不可忽略的变量。不能用 S3/Qwen 的 55.73 与 O4.P3/DPV4 的 58.88 直接判断
架构优劣。若要完成独立裁判下的严格 PageIndex 对照，应复用 O4.P3 原答案，
冻结同一份 corrected questions，并以 Qwen 运行 judge-only 评分。

## 复现入口

- S3 冻结记录：`docs/S3_MAINLINE_FREEZE_20260908.md`
- PageIndex O4.P3 记录：`docs/F500_BGE_DPV4_O4P3_20260902.md`
- DPV4 correction：`scripts/remote/run_s3_full500_correction_dpv4_20260908.sh`
- Qwen correction：`scripts/remote/run_s3_full500_correction_qwen_20260908.sh`
