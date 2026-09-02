# O4.P3：balanced 50 题 no-correction 验证

日期：2026-08-31
分支：`codex/semantic-a0`
运行目录：`/opt/enterprise-rag-bench/app/outputs/pageindex_o4p3_balanced50_20260831`

## 目的与变量

本轮在与既有 BGE-small 50 题基线相同的问题集、切块、索引、rerank、PageIndex、DPV4 和 `no-correction` 口径下，验证 O4.P3 的证据选择稳定性：

- `evidence_selection_fail_closed=false`，允许 selector 在低置信度时保留安全回退证据；
- 保留 `anchor_chunks=2`、`fallback_chunks=4`；
- rerank 后启用文档软池：最多补 2 个未出现文档，每文档最多 1 个 chunk，在前 8 个 chunk 后插入；
- 不锁定额外文档数量。`invalid_extra_docs` 按官方指标记录，但不作为本轮放行阻断条件。

本轮共 50 题、50/50 完成、0 条跳过、0 条 correction。评分仍由远端 DPV4 完成，因而结果适合与同口径历史结果比较，但不等同于独立裁判模型复评。

## 总体结果

| 指标 | BGE-small 基线 | O4.P3 | 变化 |
|---|---:|---:|---:|
| correctness | 68.00% | **72.00%** | **+4.00 pp** |
| completeness | 71.37% | **72.28%** | **+0.91 pp** |
| combined correctness×completeness | 62.13 | **67.30** | **+5.17** |
| document recall | 70.39% | **72.93%** | **+2.54 pp** |
| invalid extra docs | 0.17 | 0.21 | +0.04 |

软池实际在 47/50 题补入 2 个文档，3/50 题没有可补文档；所有 50 条答案均带有 `document_ids`。额外文档略有增加，但按当前打榜规则不影响最终得分，故不阻断本轮结论。

## 按题型诊断

| 题型 | correctness 基线→O4.P3 | completeness 基线→O4.P3 | 结论 |
|---|---:|---:|---|
| basic（18） | 72.22% → **83.33%** | 80.19% → 76.02% | 正确题增加 2 题，召回改善；个别答案更短 |
| semantic（12） | 58.33% → **58.33%** | 64.05% → 66.07% | 仍是主要瓶颈，软池没有带来正确率净增益 |
| intra-document（4） | 75.00% → **100.00%** | 87.50% → 100.00% | 多事实保留明显受益 |
| project-related（4） | 50.00% → 50.00% | 56.95% → 57.91% | 正确率不变，recall 39.58%→36.11%，仍需 raw-miss 诊断 |
| constrained（3） | 100.00% → **100.00%** | 90.11% → 95.24% | 无正确率回退，稳定性良好 |
| conflicting_info（2） | 100.00% → 50.00% | 54.16% → 54.16% | `qst_0413` 回退，需单独复核 conflict 契约/证据优先级 |

题级别上，`qst_0022`、`qst_0041`、`qst_0322` 从错误变为正确；`qst_0413` 从正确回退。semantic 仍有 `qst_0184`、`qst_0231` 等 raw recall=0 的失败样本，说明当前改动主要改善了证据选择/生成托底，尚未解决候选池覆盖。

## 结论与放行判断

1. O4.P3 对整体指标有稳定正收益，尤其是 basic 和 intra-document；constrained 未回退，说明 `fail_closed=false + fallback` 没有普遍清空有效证据。
2. semantic correctness 仍为 7/12，project-related 仍为 2/4；因此不能把本轮解释为核心检索已解决，也不能直接据此申请 F500。
3. `qst_0413` 的 conflicting_info 回退是当前必须保留的回归门槛。下一轮应先做 conflict 单变量复核，确保来源优先级已解决的冲突进入 `resolved_conflicts` 后不再触发错误阻断。
4. 在冲突回退修复后，优先做 semantic/project raw-miss 的通用候选补召回实验（原始 BM25+dense 永不丢弃，shadow 查询仅追加候选），再以同一 balanced 50 题复测；只有 semantic correctness 或 raw recall 有净增益且控制题无回退，才进入更大样本。

## 可复核产物

- 配置：`configs/eval_pageindex_o4p3_balanced50_20260831.yaml`
- 配置生成器：`scripts/cfggen/prepare_o4p3_balanced50_20260831.py`
- 远端运行脚本：`scripts/remote/_run_o4p3_balanced50_20260831.sh`
- 远端评分：`results.json`（`--no-correction --parallelism 4`）
- 远端答案与追踪：`answers.jsonl`、`route_trace.jsonl`、`simple_metrics.json`
