# O4.P2：soft pool +2 与 selector 预算保护（2026-08-31）

## 实验设置

在 O4.P 的文档软融合基础上，仅将 `generation.evidence_selection_candidate_chunks` 从 **24 提高到 30**；soft pool 仍为最多追加 2 个未覆盖文档、每文档 1 个代表 chunk。BGE-small 索引、BM25+dense+RRF、rerank、PageIndex、DPV4、题集和官方 `no-correction` 均保持一致。

同样的 20 题 soft pool 关闭控制组用于配对比较。两次生成均为独立 DPV4 调用，存在服务端/生成漂移，因此结果用于判断方向，不作为 500 题最终增益承诺。

## 官方评分

| 指标 | 控制组 | O4.P2 | 变化 |
|---|---:|---:|---:|
| correctness | 60.00% | **80.00%** | +20.00pp |
| completeness | 63.98% | **77.07%** | +13.09pp |
| combined | 56.48 | **71.48** | +15.00 |
| document recall | 59.58% | **73.33%** | +13.75pp |
| invalid extra docs | 0.15 | 0.35 | +0.20 |

20/20 题均完成，0 skipped、0 corrected。basic 控制题仍为 3/3 正确，未见基础路径回退。

## 题型观察

- `intra_document_reasoning`：相对控制组 correctness 33.33% → 100%，completeness 33.33% → 100%，召回 33.33% → 100%。
- `project_related`：correctness 66.67% → 100%，召回 63.89% → 72.22%，但 completeness 从 80.00% 降至 68.75%，新增文档带来部分噪声。
- `completeness`：控制组 0/2，O4.P2 恢复 1/2；仍不足以证明稳定改善。
- `semantic`：correctness 66.67% → 33.33%，`qst_0176` 仍然回退；提高 selector 候选预算没有解决该题。
- `constrained`：correctness 100% → 50%，且平均无效额外文档升至 2.5，说明宽松候选对约束题有明显污染风险。

## 诊断结论

扩大 selector 候选预算在本轮总体结果较好，但不能单独解释为“预算修复成功”：O4.P、O4.P2 是不同 DPV4 运行，且 semantic/constrained 仍有回退。`qst_0176` 的目标文档在最终候选前列却仍未被 selector 采用，表明问题还包括 selector 的相关性判断/拒答策略，而非单纯的 24 项截断。

同时，invalid extra docs 从 0.15 上升到 0.35，尤其 constrained 题出现明显额外文档，不能直接把 `candidate_chunks=30` 和 soft pool 一起推广到 F500。

## 下一步建议

进入 O4.P3：采用预算感知软融合，不再无条件追加两个文档：

1. 仅当新增文档有独立 rerank 支持且不会把原候选有效文档移出 selector 窗口时才追加；
2. 对 semantic/constrained 限制为最多 1 个新增文档；
3. 保持 selector 预算 30，继续记录目标文档保留、selector 空集、invalid extra docs；
4. 先做 10 题针对性 smoke，控制 semantic 回退后再进行 50 题验证。

产物目录：`outputs/pageindex_o4p2_soft_pool_smoke20_20260831/`。
