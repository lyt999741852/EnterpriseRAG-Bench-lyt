# O1：通用检索托底 Original Candidate Reserve Smoke（2026-08-31）

## 实验定义

- **基线**：当前 BGE-small 384 维 ES 索引、BM25+dense+RRF、remote rerank、PageIndex、DPV4、`no-correction`。
- **单变量**：PageIndex 返回结果后，额外插入最多 4 个 PageIndex 之前的原始 post-rerank 候选；不使用题型标签、不锁定目标文档。
- **插入策略**：每 4 个 PageIndex 结果插入 1 个原始候选，reserve 仅作为生成前候选托底。
- **范围**：20 题（12 Semantic、4 Completeness、Project/Constrained/Conflict/Basic 各 1）。
- **远端产物**：`/opt/enterprise-rag-bench/app/outputs/pageindex_o1_original_reserve_smoke20_20260831`

## 结果

| 指标 | 同 20 题基线 | O1 reserve | 变化 |
|---|---:|---:|---:|
| correctness | 15.00% | **35.00%** | +20.00pp |
| completeness | 27.83% | **34.90%** | +7.07pp |
| combined | 13.08 | **27.27** | +14.19 |
| document recall | 7.14% | **20.48%** | +13.34pp |
| 平均无效额外文档 | 1.00 | 1.50 | +0.50 |

候选保留实际生效：19/20 题各插入 4 个 reserve chunk，共 76 个；1 题没有可新增的 reserve。

## 题型信号

- Semantic 12 题：correctness 33.33%、recall 25.00%；`qst_0197`、`qst_0272` 的正确性和 recall 恢复。
- Completeness 4 题：correctness 50.00%、recall 14.88%；`qst_0447` 恢复，但 `qst_0450` completeness 由 100% 降至 0%。
- `qst_0410` Constrained：completeness 由 55.56% 降至 33.33%，属于控制题回退。
- `qst_0050` Basic：本轮与基线无指标变化。

## 隔离性与放行判断

本轮 **O1 不放行、不合流**，原因有两点：

1. 虽然目标子集指标上升，但出现 Constrained/Completeness 控制回退，且无效额外文档增加。
2. PageIndex/LLM 重跑存在非确定性路由漂移：例如 `qst_0410` 在基线和 O1 中均走 `pageindex_admitted`，但候选文档集合不同；这说明单次重跑不能把全部差异归因于 reserve 插入。

因此本轮只证明“在部分 PageIndex 结果之后保留原始候选，可能恢复少数目标题”，尚未证明该机制在严格隔离下稳定提升。它也无法修复 raw-miss 或 rerank 阶段丢失，因为 reserve 来源是 post-rerank 候选。

## 后续动作

1. 保留 O1 作为失败/探索记录，不接入主链，不运行 F500。
2. O2 改为先做固定候选集的离线 replay：锁定同一 raw/pre-rerank/PageIndex 输入，只比较候选 admission 和 evidence selection，消除 PageIndex 重跑漂移。
3. 若 replay 仍有净增益，再设计低置信度触发的通用 reserve；若控制题仍回退，放弃“无条件插入 reserve”。
