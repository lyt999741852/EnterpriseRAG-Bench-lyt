# O4.P：文档软融合生成 smoke（2026-08-31）

## 实验设置

本轮使用 20 题分层样本（basic、semantic、intra-document reasoning、project-related、constrained、conflicting_info、completeness、miscellaneous），保持 BGE-small 384 维索引、BM25+dense+RRF、rerank、PageIndex、DPV4 和官方 `no-correction` 不变。

唯一变量是生成前的文档级 soft pool：从同题 rerank 结果中追加最多 2 个原候选未覆盖文档的代表 chunk，每个新增文档最多 1 个 chunk；不使用 gold 文档、不做 strict drop。另跑同题 soft pool 关闭控制组。

## 官方评分（同题配对）

| 指标 | 控制组 | O4.P | 变化 |
|---|---:|---:|---:|
| correctness | 60.00% | 65.00% | +5.00pp |
| completeness | 63.98% | 69.53% | +5.55pp |
| combined | 56.48 | 61.38 | +4.90 |
| document recall | 59.58% | 68.33% | +8.75pp |
| invalid extra docs | 0.15 | 0.10 | -0.05 |

两组均为 20/20 完成、0 skipped、0 corrected。基础题 3/3 两组均正确，说明策略没有破坏最简单的控制路径。

## 题型信号

- `project_related`：correctness 66.67% → 100%，completeness 80.00% → 89.17%。
- `intra_document_reasoning`：correctness 持平 33.33%，completeness 33.33% → 55.56%，召回 33.33% → 66.67%。
- `completeness`：召回 0% → 50%，但样本仍未产生正确答案。
- `semantic`：66.67% → 33.33%，出现明显回退；`constrained`：100% → 50%，也出现回退。
- `conflicting_info` 在本小样本中由 0% → 100%，但只有 2 题，且 DPV4 生成存在运行漂移，不能单独外推。

## 关键诊断

O4.P 暴露了一个比“是否追加候选”更重要的预算问题：虽然 soft pool 在检索结果层是只增不删，但现有 `evidence_selection_candidate_chunks=24` 会对追加后的列表重新做有界截断。某些题的原始有效 chunk 排名靠后，插入新增文档后被挤出 selector 可见窗口，导致 selector fail-closed 或选择了不完整证据。

典型例子是 `qst_0176`：控制组保留目标文档并得到部分正确答案；O4.P 追加两个文档后，最终 selector 没有可用目标证据，答案变为证据不足拒答。相反，`qst_0302`、`qst_0411` 等题因新增文档进入可见窗口而得到恢复。

因此本轮不能把 soft pool 直接合入正式 500 题配置。它证明了“文档覆盖”有收益，但也证明了必须配套预算保护，否则 semantic/constrained 会发生回退。

## 下一步

进入 O4.P2：保持 `max_extra_docs=2`，只增加 selector 候选预算（24 → 28 或 30），并记录目标文档是否因候选窗口截断而消失；同时保留 basic、semantic、constrained 作为控制。若 semantic/constrained 不再回退，再做 50 题 no-correction 验证。若仍回退，则改为“只在新增文档能进入候选预算时追加”的预算感知 soft pool，而不是继续扩大候选池。

产物：

- O4.P：`outputs/pageindex_o4p_soft_pool_smoke20_20260831/`
- 控制组：`outputs/pageindex_o4p_control_smoke20_20260831/`
- 配置：[eval_pageindex_o4p_soft_pool_smoke20_20260831.yaml](../configs/eval_pageindex_o4p_soft_pool_smoke20_20260831.yaml)
- 运行脚本：[\_run_o4p_soft_pool_smoke20_20260831.sh](../scripts/remote/_run_o4p_soft_pool_smoke20_20260831.sh)
