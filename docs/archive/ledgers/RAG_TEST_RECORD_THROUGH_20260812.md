# EnterpriseRAG 测试总记录（截至 2026-08-12）

> 续记：下方新增 2026-08-12～13 的 Qwen3/Conan 评测与 BGE 回退实验。

## 0. 2026-08-12～13 新增结论

### Qwen3/Conan 新向量库

索引审计确认：ES 3,084,120 条物理向量记录都可在剥离任意层 `__pN`
后追溯到当前 1,075,100 个缓存基础 chunk，差异来自 Conan 512-token
窗口下的递归二分，不是旧版本数据混入。

| 实验 | 范围 | correctness | completeness | combined | recall | extra |
|---|---:|---:|---:|---:|---:|---:|
| Q3-A：Qwen3，无 rerank | 50 | 42.0 | 43.64 | 37.41 | 40.78 | 0.23 |
| Q3-B：Qwen3 + remote rerank | 50 | 40.0 | 40.05 | 36.41 | 43.85 | 0.15 |
| A1：query instruction，dense=0.3 | basic-18 | 22.22 | 23.61 | 18.06 | 27.78 | 0.06 |
| A2：query instruction，dense=0.5 | basic-18 | 33.33 | 29.17 | 29.17 | 33.33 | 0.06 |

结论：query instruction 没有相对 Q3 basic 基线产生可测变化；dense=0.5
有局部改善，但整体仍远低于 BGE。Qwen3/Conan 不再作为当前优化主线。

### 回退 BGE 后的 B1

| 实验 | 范围 | correctness | completeness | combined | recall | extra |
|---|---:|---:|---:|---:|---:|---:|
| B1：BGE + rerank，dense=0.5 | basic-18 | 72.22 | 75.46 | 70.83 | 72.22 | 0.17 |

B1 相对历史 BGE basic 主链没有提升：正确率持平，完整度/召回下降，extra
上升。主线继续保留 `dense_weight=0.3`，下一候选实验是只扩大 rerank 前
hybrid 候选深度。

本文整合历史 V5.2 主线与 2026-08-10～12 的 BGE、rerank、查询改写、多视图、PageIndex 路由实验。后续实验以本文作为指标台账，以 `../handoffs/NEXT_TEST_HANDOFF_20260812.md` 作为执行交接。

## 1. 统一口径

- 官方质量指标来自 EnterpriseRAG-Bench `metrics_based_eval`：correctness、completeness、combined、document recall、invalid extra docs。
- 10 题锚点集与 50 题分层集不可横向比较绝对分数；二者用途不同。
- 50 题集按 500 题总体比例分层：basic 18、semantic 12、intra-document 4、project 4、constrained 3、conflicting/completeness/misc/info-not-found 各 2、high-level 1。
- 官方评分必须使用已安装官方依赖的环境；历史上 `embedding_test` 缺 `openai` 曾制造假 0 分。
- LLM 温度为 0 仍不保证逐字确定：远程服务版本、并发顺序、重试、PageIndex LLM 规划均可能引入小幅波动。2～5pp 差异应通过同代码同日复跑确认。

## 2. 历史 V5.2 基线（已确认版本名）

### V5.2 10 题锚点（2026-08-03）

配置：`configs/eval_pageindex_balanced10_v52.yaml`

| correctness | completeness | combined | recall | invalid extra |
|---:|---:|---:|---:|---:|
| 90.0% | 77.33% | 77.33 | 87.50% | 0.12 |

用途：小规模回归锚点；9/10 正确，仅 qst_0480 失败。该结果曾用正确官方环境稳定复现。

### V5.2 50 题分层（2026-08-03）

配置：`configs/eval_pageindex_balanced50_v52.yaml`

| correctness | completeness | combined | recall | invalid extra |
|---:|---:|---:|---:|---:|
| 58.0% | 59.21% | 54.41 | 61.70% | 0.15 |

用途：泛化基线。不可把上面的 10 题 90% 写成 V5.2 的 50 题成绩。

### P1 partial-open 50 题

配置：`configs/eval_pageindex_balanced50_p1.yaml`

| correctness | completeness | combined | recall | invalid extra |
|---:|---:|---:|---:|---:|
| 60.0% | 59.19% | 54.66 | 59.81% | 0.19 |

P1 对 10 题与 V5.2 逐字相同；50 题没有形成决定性净增益。

## 3. 2026-08-10～12 新实验台账（BGE-small 旧库）

旧库固定信息：`enterprise-rag-bge-small-v1`，928,534 chunks，fixed-v2 512/0，BGE-small 384 维。以下 50 题使用同一分层题集。

| 实验 | 范围 | correctness | completeness | combined | recall | extra | 结论 |
|---|---:|---:|---:|---:|---:|---:|---|
| BGE + PageIndex（无 rerank） | 50 | 58.0 | 58.43 | 54.66 | 58.39 | 0.26 | 近期基础对照 |
| **BGE + remote rerank** | **50** | **62.0** | **66.49** | **58.74** | **66.19** | 0.17 | **近期 50 题最佳，当前回退点** |
| 全题型多视图 + rerank | 50 | 60.0 | 60.96 | 56.41 | 61.94 | **0.13** | 路数过多稀释强信号，不采用 |
| 选择性 PageIndex | 50 | 32.0 | 40.39 | 31.67 | 39.18 | 0.21 | 绕过 PageIndex/证据结构严重回退，不采用 |

近期最佳配置：`configs/eval_pageindex_balanced50_bge_rerank_cpu.yaml`。注意：其名称中的 rerank-only 表示“仅新增 reranker 的 A/B”，PageIndex 仍由 `EvidencePlanner` 按题型决定是否实际执行；basic/misc/info-not-found 本来就不进入 PageIndex。

### 3.1 rerank 增益（相对无 rerank）

- correctness +4.0pp；completeness +8.06pp；combined +4.08；recall +7.80pp；extra -0.09。
- basic：66.67/65.83/66.67 → 72.22/82.13/77.78（correct/complete/recall）。
- semantic：25.0/27.78/33.33 → 33.33/37.50/41.67。
- completeness：0/4.54/8.34 → 50.0/13.63/41.66。

### 3.2 semantic 专项实验

| 实验 | correctness | completeness | combined | recall | 结论 |
|---|---:|---:|---:|---:|---|
| 无 rerank 的语义分解 | 33.33 | 36.11 | 31.94 | 41.67 | 相对早期 semantic 基线提升，但非同 rerank 条件 |
| 低权重分解 + rerank | 33.33 | 37.50 | 33.33 | 41.67 | 与 rerank 基线完全持平 |
| 后 rerank 证据配额 | 33.33 | 37.50 | 33.33 | 41.67 | 12/12 最终答案与基线相同；注入证据未穿透 PageIndex |
| ES 直连事实面（绕过 PageIndex） | 8.33 | 8.33 | 8.33 | 16.67 | 系统性失败，不采用 |

经验：semantic 的多路结果不能只在 PageIndex 前做 RRF/配额。若继续优化，应在 PageIndex 内保留“事实面 → 独立候选文档 → 节点 → 缺口追问”的归属关系。

### 3.3 basic 专项实验

18 个 basic 题隔离测试：`configs/eval_basic18_bm25_dense_rewrite_rrf_rerank_direct_cpu.yaml`。

| 实验 | correctness | completeness | combined | recall | extra |
|---|---:|---:|---:|---:|---:|
| 普通 ES 直连（选择性实验中的 basic） | 33.33 | 39.07 | — | 38.89 | — |
| BM25 1.0 + 原 dense 1.0 + 改写 dense 0.35 + RRF + rerank | 66.67 | 68.06 | 65.28 | 66.67 | 0.11 |
| 近期 rerank 基线中的 basic | 72.22 | 82.13 | — | 77.78 | 0.11 |

重要修正：`EvidencePlanner` 对 basic 的 `use_pageindex=false`。因此 basic 差异不能归因为 PageIndex；应归因于检索组合、候选深度、代码/服务运行版本等。下一步需在当前代码和同一时段做严格三组消融：

1. BM25 0.7 + dense 0.3，无改写；
2. BM25 1.0 + dense 1.0，无改写；
3. BM25 1.0 + dense 1.0 + 改写 dense 0.35。

## 4. 当前框架的准确描述

1. 原问题通过 ES BM25/dense 检索并以 RRF 融合。
2. 远程 reranker 将宽候选重排到 30 chunks。
3. `EvidencePlanner` 按题型控制 PageIndex：basic/misc/info-not-found 不使用；semantic/intra/constrained/conflicting/project/completeness/high-level 使用不同候选文档、节点和跳数上限。
4. PageIndex 按 rerank 顺序对 `doc_id` 去重，从 manifest 读取候选完整原文；构建或复用内容指纹缓存的标题—章节树。
5. PageIndex LLM 生成 facets、hard constraints、risk dimensions、search queries；节点选择器将节点绑定到 facet；审计后仍缺 facet 才向 ES 发起补充检索。
6. 多跳是“新的 ES 查询 → 新 chunks/doc IDs → 重建候选树 → 重选/审计节点”，不是节点图上的直接跳边。
7. Generator 对 PageIndex 节点或 ES chunks 做证据选择、草稿生成、事实核验、最终答案与引用审计。

## 5. 已否定或尚未证明的方向

- 全题型同时加入关键词、原语义、改写语义、答案意图：无净增益。
- semantic 在 PageIndex 前增加 RRF 权重或证据配额：无净增益。
- semantic 绕过 PageIndex：显著回退。
- 按题型外部强制绕过 PageIndex：50 题显著回退；且与 Planner 内部路由重叠，设计上应统一到 Planner。
- “dense 等权有效”与“改写有效”尚未被单变量分离；basic 1/1/0.35 的提升不能全部归功于改写。

## 6. 可复现产物约定

每轮输出目录必须保存：`answers.jsonl`、`results.json`、`route_trace.jsonl`、`simple_metrics.json`、`validation.json`、`run_meta.json`。比较小于 5pp 时，应在同代码、同服务、独立 cache/output 名称下至少复跑一次。
