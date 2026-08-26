# Semantic30 S1 A0 失败层诊断

日期：2026-08-25（Asia/Shanghai）

配置：`configs/eval_semantic30_r4_s1_lexical_anchor_20260820.yaml`

范围：固定 30 道 Semantic 题，PageIndex OFF；仅对既有 S1 评测产物做离线诊断。

## 前置核验

- BGE Elasticsearch、reranker、研究 embedding 和 LLM 均返回 HTTP 200。
- BGE manifest 存在且非空；S1 的 answers、route trace、评分结果均为 30 条。
- 未发现正在运行的 pipeline 或官方评分进程。

## 结果

| 失败层 | 题数 | 占比 | Question IDs |
|---|---:|---:|---|
| Raw miss | 9 | 30.0% | qst_0180, qst_0184, qst_0204, qst_0212, qst_0220, qst_0240, qst_0248, qst_0260, qst_0268 |
| RRF/rerank drop（未恢复） | 3 | 10.0% | qst_0196, qst_0256, qst_0276 |
| Selector/citation drop | 2 | 6.7% | qst_0176, qst_0272 |
| Generation/fact-coverage gap | 4 | 13.3% | qst_0189, qst_0200, qst_0208, qst_0232 |
| Fully successful | 12 | 40.0% | 其余 12 题 |

有 1 题在主 RRF/rerank 路径中丢失目标文档，但被现有语义补救找回，最终答案、完整性和引用均为满分；该题计入成功，不作为未解决检索失败。

## 结论与下一步

诊断确认最大、且最适合 A1 单变量检验的问题是 **raw miss（9 题）**：目标文档没有进入任何原始检索 view。下一步仅设计受约束的 Semantic bridge query，用题干已有实体、系统、事件和关系来补充检索表达；不使用答案、gold document ID 或真实 benchmark 题型参与线上链路。

离线逐题明细保存在本地/远端实验输出的 `failure_layers.json`，包含用于审计的期望文档字段，不纳入 Git 提交。
