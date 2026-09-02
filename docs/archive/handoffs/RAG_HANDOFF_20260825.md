# EnterpriseRAG-Bench RAG 优化交接（当前有效状态）

> 更新时间：2026-08-25（Asia/Shanghai）  
> 用途：新会话的唯一续接入口。先读本文件，再按“续接顺序”读取指定配置和报告。  
> 口径：除特别注明外，分数均由上游官方 `metrics_based_eval` 以 `--no-correction` 计算；它是可重复的内部对照口径，不等同于公开榜单的最终校正口径。

## 1. 当前决策与不可变边界

- **主线索引与架构：BGE-small + BM25 + remote rerank + PageIndex。** 不替换为 Conan/Qwen。
- **保留 PageIndex。** 严格 AB50 证明它带来很大的整体收益；Semantic 的召回问题不能靠删掉 PageIndex 解决。
- **优化分两条并行但隔离的路线：**
  1. Semantic 专项：先在固定 Semantic30、PageIndex OFF 的隔离试验台定位和修复“目标文档未进候选”的问题；通过门槛后才接回 PageIndex ON 主链。
  2. 全局稳健增益：以 PageIndex ON 的固定 50 题及定向题集为门禁，改善 Basic、Project Related、Completeness，且不改变 Semantic 专项的实验配置。
- **Conan/Qwen 仅保留为研究资产。** 不能作为主线、不能直接跑新的全量 500；只有先证明它能补回 BGE 漏掉的 Semantic 目标文档，才有资格做低权重影子召回。
- **E5 secondary 分支无效且已清理。** E5 ES 索引和缓存曾不完整，已删除；不得引用 D2b 的结果，也不得再次启用 `eval_semantic30_r4_d2b_e5_secondary_20260825.yaml`。
- 不使用 benchmark 的 `question_type`、参考答案、gold facts、gold document IDs 或校正后的题目内容参与在线路由、检索、PageIndex 或生成。真实题型仅用于离线分桶和评分。

## 2. 当前主线 RAG 架构

```text
question-only
  -> LLM 推断检索需求/题型（非 benchmark 标签）
  -> BM25 + BGE dense +（仅指定路由）rewrite/answer-intent dense
  -> 带权 RRF 融合
  -> remote cross-encoder rerank
  -> semantic rescue（严格共识、最多新增 1 文档）
  -> PageIndex 文档树 / 节点审计 / 有界补检索（部分题型）
  -> precision_v3 证据选择
  -> LLM 生成 -> 事实核验 -> 最终答案/来源审计
  -> answers.jsonl -> 官方 metrics_based_eval
```

### 2.1 路由与题型检索配置

| 内部路由（由问题文本推断） | 多视图检索 | PageIndex 证据模式 | 后续优化边界 |
|---|---|---|---|
| `basic`、`miscellaneous` | BM25 + 原问题 BGE dense | 不进入 | 可优化回答覆盖和引用精度；不改全局权重 |
| `info_not_found` | BM25 + 原问题 BGE dense | 不进入，证据不足导向拒答 | 回归保护，避免误答 |
| `semantic` | BM25 + 原问题 dense + rewrite dense + intent dense | `single_semantic`，1 个目标文档、最多 1 跳 | 专项路线；不得硬锁单一候选文档 |
| `intra_document_reasoning` | BM25 + 原问题 dense | `single_multisection`，同文档多章节、最多 2 跳 | 仅回归保护 |
| `constrained` | BM25 + 原问题 dense | `constrained_pair` | 仅回归保护 |
| `conflicting_info` | BM25 + 原问题 dense | `conflict_pair` | 仅回归保护；重点防止版本证据丢失 |
| `project_related` | 四路检索 | `multi_hop`，最多 3 文档、2 跳 | 项目/组件/路径词法锚点与链路覆盖 |
| `completeness` | BM25 + 原问题 dense + intent dense | `exhaustive`，对象去重和缺失分面补检索 | 完整覆盖、去重、计数审计 |
| `high_level` | BM25 + 原问题 dense | `corpus_level` | 仅回归保护 |

### 2.2 BGE 主线关键参数（不得在同一实验混改）

| 层 | 当前值 |
|---|---|
| 文档切块 | `fixed-v2`，512 tokens，overlap 0 |
| embedding | `BAAI/bge-small-en-v1.5`，384 维，CPU |
| ES 索引 | `enterprise-rag-bge-small-v1`，`read_existing_index: true` |
| 融合 | RRF，`rrf_k=60`，BM25 1.2、原始 dense 1.0、rewrite 0.9、intent 0.4 |
| stable hybrid | `candidate_k=240`，`dense_weight=0.3` |
| reranker | 远端 bge-reranker-v2-m3，`120 -> 30` |
| semantic rescue | 1 rewrite + 1 intent；每路 8；共识文档 2；最多新增文档 1 |
| PageIndex | 全局候选文档 24、每文档节点 40、最多 2 跳；Semantic 最多 1 跳 |
| 证据选择 | `precision_v3`，候选 24、最终 10、每文档最多 4，`fail_closed=true` |
| 生成 | Lark/Qwen3.5-27B-AWQ 兼容 API，温度 0，最大 8192 tokens |

完整架构与代码位置见 [`docs/BGE_RAG_ARCHITECTURE_REPORT_20260820.md`](docs/BGE_RAG_ARCHITECTURE_REPORT_20260820.md)。

## 3. 有效、可比较的测评结果

### 3.1 当前最佳完整 500 题基线（冻结，不覆盖）

配置快照：[`configs/snapshots/eval_pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817.yaml`](configs/snapshots/eval_pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817.yaml)  
快照校验与题集：[`configs/snapshots/BGE500_NO_CORRECTION_SNAPSHOT_20260818.json`](configs/snapshots/BGE500_NO_CORRECTION_SNAPSHOT_20260818.json)

| RAG System | Overall Score | Answer Correctness | Answer Completeness | Document Recall | Invalid Extra Docs |
|---|---:|---:|---:|---:|---:|
| BGE + Rerank + LLM Route + Multiview + PageIndex | **55.18** | 60.60 | 62.57 | 61.12 | 0.18 |

此分数是当前最可靠的 500 题结果，也是后续任何全量候选的最低对照线。

### 3.2 500 题按题型结果与优先级

| 题型 | 题数 | 正确性 | 完整性 | 综合分 | 文档召回 | 无效额外文档 | 判断 |
|---|---:|---:|---:|---:|---:|---:|---|
| Basic | 175 | 68.57 | 67.92 | 64.40 | 71.43 | 0.11 | 主力优势；小幅提升也有全局价值 |
| Semantic | 125 | 42.40 | 41.21 | 38.10 | 42.40 | 0.29 | 第一优先级；主要是目标文档未进入候选 |
| Intra-Document Reasoning | 40 | 72.50 | 82.23 | 70.42 | 90.00 | 0.07 | 强项，只做回归保护 |
| Project Related | 40 | 37.50 | 46.74 | 25.87 | 41.87 | 0.35 | 第二短板，需专项检索/链路覆盖 |
| Constrained | 30 | 70.00 | 85.09 | 66.89 | 78.33 | 0.03 | 强项，只做回归保护 |
| Conflicting Info | 20 | 70.00 | 69.06 | 60.09 | 37.50 | 0.05 | 答案尚可但召回偏低，做回归保护 |
| Completeness | 20 | 45.00 | 37.66 | 25.83 | 32.57 | 0.55 | 第三短板，需穷举/去重/覆盖优化 |
| Miscellaneous | 20 | 95.00 | 84.00 | 84.00 | 95.00 | 0.00 | 强项 |
| High Level | 10 | 40.00 | 72.17 | 40.00 | 0.00 | 小样本，不单独调参 |
| Info Not Found | 20 | 95.00 | 100.00 | 95.00 | 0.00 | 强项，严格保护 |

全局收益估算：Semantic 每提升 10 综合分，约带来 **+2.5** 全局分；Basic 每提升 5 分，约 **+1.75**；Project Related 每提升 10 分，约 **+0.8**；Completeness 每提升 10 分，约 **+0.4**。因此资源分配建议为：Semantic/Project/Completeness 约 70%，Basic 的低风险完善约 30%。

### 3.3 固定 50 题与 PageIndex 严格 AB

固定分层 50 题历史基线：

| RAG System | Overall Score | Answer Correctness | Answer Completeness | Document Recall | Invalid Extra Docs |
|---|---:|---:|---:|---:|---:|
| BGE 主线历史 50 | 59.14 | 64.00 | 65.49 | 60.87 | 0.23 |

严格 AB 使用同一 50 个问题、同一 BGE/检索/生成/评分链，仅改变 `pageindex.enabled`：

| 配置 | Overall Score | Answer Correctness | Answer Completeness | Document Recall | Invalid Extra Docs |
|---|---:|---:|---:|---:|---:|
| PageIndex ON r3 | **59.34** | 64.00 | 65.15 | 61.76 | 0.17 |
| PageIndex OFF r3 | 45.17 | 46.00 | 57.21 | 58.69 | 0.26 |
| ON - OFF | **+14.17** | +18.00 | +7.94 | +3.07 | -0.09 |

配置：[`configs/eval_pageindex_ab50_semantic_consensus_20260820_r3_on.yaml`](configs/eval_pageindex_ab50_semantic_consensus_20260820_r3_on.yaml)、[`configs/eval_pageindex_ab50_semantic_consensus_20260820_r3_off.yaml`](configs/eval_pageindex_ab50_semantic_consensus_20260820_r3_off.yaml)。

结论：PageIndex 是全局主链组成，不应移除；但它只会处理已进入候选的文档，不能替代 Semantic 的首阶段召回。

### 3.4 Semantic30（PageIndex OFF）有效结果

此试验台刻意关闭 PageIndex，用来隔离初始检索、rerank 和证据选择；**不能与 500 主链分数横向比较**。

| 实验 | 改动 | 正确性 | 完整性 | 综合分 | 召回 | 无效额外文档 | 结论 |
|---|---|---:|---:|---:|---:|---:|---|
| Baseline OFF | 无 | 46.67 | 49.62 | 42.22 | 50.00 | 0.63 | 专项基线 |
| S1 Lexical Anchor | Semantic 路由中 BM25 1.2→1.5；rewrite 0.9→0.8；intent 0.4→0.25 | **50.00** | **53.30** | **45.56** | **53.33** | 0.53 | 当前有效最佳 |
| S2 Parent Window | S1 + 父窗口策略 | 50.00 | 53.30 | 45.56 | 53.33 | 0.53 | 无增益，不采用 |
| S3 Anchor Rescue | S1 + 文档保留/补救 | 50.00 | 52.38 | 44.89 | 53.33 | 0.57 | 退化，不采用 |
| D1 Document First | 先硬选目标文档再推理 | 40.00 | 41.06 | 35.17 | 40.00 | 0.23 | 明显退化，禁止复用 |
| D2a Wide Candidates | 仅扩大候选池 | 50.00 | 52.12 | 45.56 | 53.33 | 0.63 | 无净增益，不采用 |

错误审计（S1）：30 题中约 12 个核心失败是所有原始视图都未召回目标文档；约 3 个是目标已在原始候选、但在 RRF/rerank 后被挤出；约 2 个是证据选择/引用遗漏；约 4 个是已有证据但生成/事实覆盖不足。下一轮首先要验证“原始候选缺失”能否被专属检索桥接补回。

### 3.5 Conan/Qwen 向量路线（有效的反例，不作为主线）

| 配置/题集 | 正确性 | 完整性 | 综合分 | 召回 | 无效额外文档 |
|---|---:|---:|---:|---:|---:|
| BGE P0，分层 100 | **63.00** | **65.70** | **58.83** | **61.00** | 0.17 |
| Conan/Qwen V3 P0，分层 100 | 53.00 | 56.56 | 48.42 | 53.11 | 0.18 |
| Conan/Qwen V3 P0-1，关闭递归分区归并 | 52.00 | 55.14 | 47.42 | 50.98 | 0.18 |
| Conan/Qwen V3 P0-2，扩大候选池 | 55.00 | 57.34 | 50.72 | 54.31 | 0.17 |
| 早期 Q3-A 50，无 rerank | 42.00 | 43.64 | 37.41 | 40.78 | 0.23 |
| 早期 Q3-B 50，remote rerank | 40.00 | 40.05 | 36.41 | 43.85 | 0.15 |

Conan/Qwen 使用的是**相同 EnterpriseRAG 语料**，并非“换数据集”；变化是 1792 维 embedding 和 448 token / 32 overlap 的切块、向量库与检索排序。P0-2 有局部改善，但较 BGE P0 仍低 8.11 综合分。

主要判断：高维不自动等于更好的问档对齐；overlap 和递归 `__pN` 分片增加相似局部片段，容易稀释候选排序与最终上下文。P0-1 表明关闭合法的递归分区归并更差，`__pN` 本身不是数据污染。两条线的 Invalid Extra 接近，退化的核心是正确证据没有稳定进入上下文，不是额外文档过多。

## 4. 当前资源与配置清单

### 4.1 在线服务与索引

| 资源 | 地址/名称 | 当前状态 | 使用规则 |
|---|---|---|---|
| BGE ES | `http://127.0.0.1:9200` / `enterprise-rag-bge-small-v1` | 主线完整，约 928,534 向量记录 | 只读查询；禁止重建/覆盖 |
| BGE 缓存/manifest | `.index_cache/full_es_bge_small/manifest.sqlite3` | 主线完整 | PageIndex 回读原文的唯一主线 manifest |
| reranker | `http://10.72.55.209:7992/v1/rerank` | bge-reranker-v2-m3 | 所有主线对照固定使用 |
| LLM | `http://10.72.100.35:7777/v1` / `lark` | Qwen3.5-27B-AWQ 兼容服务 | 路由、改写、PageIndex、生成及当前内部评分 |
| Conan embedding | `http://10.72.55.209:7993/v1` / `embedding` | 1792 维服务可用 | 仅研究性 shadow 分支；不要替主线 BGE |
| Conan V3 ES | `http://10.72.100.29:31920` / `enterprise-rag-qwen3-emb-v3-conan448` | 完整，3,030,317 记录 | 保留追溯；不跑全量 |
| Qwen v2 ES | `http://10.72.100.29:31920` / `enterprise-rag-qwen3-emb-v2` | 约 3,084,120 记录 | 历史研究资产 |
| E5 ES/cache | 已删除 | 不完整时已精确清理 | 不可使用；模型目录保留不代表索引可用 |

所有密钥只能通过环境变量传入；不得写入 YAML、Markdown、输出、终端摘录或新的交接文档。

### 4.2 重要配置与产物

| 用途 | 文件/目录 |
|---|---|
| 冻结 500 主线 | `configs/snapshots/eval_pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817.yaml` |
| 500 快照及 hash | `configs/snapshots/BGE500_NO_CORRECTION_SNAPSHOT_20260818.json` |
| BGE 100 对照 | `configs/eval_pageindex_stratified100_bge_rerank_question_only_llm_route_multiview_p0_20260814.yaml` |
| PageIndex ON/OFF AB50 | `configs/eval_pageindex_ab50_semantic_consensus_20260820_r3_on.yaml` / `_off.yaml` |
| Semantic30 S1 基线 | `configs/eval_semantic30_r4_s1_lexical_anchor_20260820.yaml` |
| 官方评分流程 | `docs/OFFICIAL_EVAL_CLOSURE_20260814.md` |
| 架构说明 | `docs/BGE_RAG_ARCHITECTURE_REPORT_20260820.md` |
| Conan 历史配置 | `conan_rag/configs/` 及 `configs/eval_pageindex_stratified100_qwen3_v3_p0_r2_candidate_pool_20260817.yaml` |

## 5. 后续两条并行但隔离的路线

### 路线 A：Semantic 专项检索（第一优先级）

**目标：** 提高目标文档进入候选集的比例，同时不把候选硬锁到单一文档、不增加全局额外文档风险。

**隔离试验台：** 固定 30 道 Semantic 题；以 S1 为基线；`pageindex.enabled: false`；其余 BGE、reranker、证据选择、评分口径保持不变。成功后才创建新的 PageIndex ON 配置做集成验证。

| 阶段 | 单变量改动 | 配置原则 | 通过门槛 | 失败处理 |
|---|---|---|---|---|
| A0 失败分桶 | 为 S1 输出补充诊断，不改变答案链 | 将每题标为 raw-miss、RRF/rerank-drop、selector-drop、generation-gap | 30 题全部可归因；确认 raw-miss 数 | 先修诊断，不能盲调参数 |
| A1 语义桥接查询 | 新增一条受约束的 Semantic bridge query | 仅抽取题干已有实体、系统、事件、因果/时序关系；不得猜答案 | raw-miss 的目标文档命中增加，且总分 >45.56 | 删除分支，不继续叠加 |
| A2 融合准入 | bridge 结果以低权重 RRF 候选进入 | 不改默认题型权重；无 hard document lock；限制每文档 chunk 数 | 召回与综合均改善，extra 不恶化超过 0.10 | 回退到 A1 或停止 |
| A3 证据覆盖 | 只处理已命中的 selector/generation-gap | 增加受控 anchor/fallback 或事实清单审计；与检索实验分开 | 分析样本覆盖改善，extra 可控 | 停止，不和 A1 混改 |
| A4 主链集成 | 将唯一通过的检索改动接回 PageIndex ON | 新 cache、同一固定 50 + Semantic 子集；其它题型不变 | ON 对照不退化，Semantic 改善 | 不进入全量 |

**明确禁止：** 复用 D1 document-first；仅因为候选池变宽而继续加深 D2a；使用已清理的 E5；以 benchmark 的真实 Semantic 标签驱动线上链路；在未通过 A4 前跑 500。

### 路线 B：全局稳健增益（与 A 隔离）

**目标：** 在 PageIndex ON 主线中提高高权重 Basic 的完整性，并分别修复 Project Related 与 Completeness 的低覆盖；不修改 Semantic 专项的实验 YAML 或缓存。

| 子路线 | 题型与测评集 | 检索/证据架构改动 | 保护项 | 通过门槛 |
|---|---|---|---|---|
| B1 Basic 覆盖 | 固定 AB50 + Basic 子集 | 不动检索权重；增加答案前事实清单/引用覆盖审计 | extra 不上升、InfoNotFound 不误答 | Basic 改善，AB50 不低于 59.34 的波动区间 |
| B2 Project | 固定 Project 题集 + AB50 | 仅该路由增加项目名、组件名、路径/版本等词法锚点；保持四路召回与 PageIndex multi-hop | 不影响 Basic/Semantic 路由 | Project 召回和综合同时改善 |
| B3 Completeness | 固定 Completeness 题集 + AB50 | PageIndex exhaustive 的对象清单、来源去重、缺失分面补检索；生成前计数/穷尽核验 | document IDs ≤10；extra 不失控 | 完整性/召回改善，extra 可控 |
| B4 回归门禁 | AB50 + 各定向题集 | 仅合并已单独通过的 B1/B2/B3 改动 | Intra、Constrained、InfoNotFound 不退化 | 所有子集通过才进入 100/500 |

**路线 B 原则：** 不对全局 `dense_weight`、默认 RRF 权重、chunk 方案或 PageIndex 开关做混合改动；每个题型路由拥有独立配置覆盖，非目标路由保持冻结主线参数。

### 两条路线的合流与 500 门槛

1. A4、B4 分别通过后，创建一个新的合流 YAML，只包含已经各自通过的开关。
2. 先在固定 AB50 和相同分层 100 上跑 pipeline + `--no-correction` 官方评分。
3. 只有 100 题对 BGE P0 的 58.83 有明确、可重复净增益，且 AB50 不退化，才启动一次新的 500。
4. 500 完成后必须分别保存原始 `answers.jsonl`、配置、运行日志、官方评分明细和每题 trace；不得覆盖 55.18 快照。
5. 进入准备提交阶段时，对同一 500 答案另建 `official_correction/`，按官方默认校正流程再跑一次；不得将 correction 与 no-correction 分数混比。

## 6. 测评协议、并行与提速规则

### 6.1 合规测评清单

- 线上输入只允许 `question_id` 与 `question`；必须设置 `pipeline.question_only: true` 和 `question_router.enabled: true`。
- 索引必须设置 `overwrite_index: false`、`read_existing_index: true`，任何评测不得重建 ES 或改写 manifest。
- 每个实验必须使用新的：YAML、`pipeline.name`、output 目录、PageIndex `cache_dir`。不能复用历史输出或 cache 路径。
- 提交/评分产物必须是每行一个 JSON 的 `answers.jsonl`：`question_id`、`answer`、`document_ids`；`document_ids` 仅能来自最终实际使用的证据。
- 快速实验固定使用官方 `metrics_based_eval --no-correction`、相同题集、相同评分模型服务与相同配置快照。
- 最终候选需另跑官方默认 correction 流程；raw JSON 仅允许隔离地提供给评测器，不能回流到 RAG。
- 当前生成与本地评分均使用 `lark`，它是内部质量门禁；公开排行榜若采用不同裁判模型，存在评分漂移，不能把本地 55.18 直接当作榜单最终分数。

### 6.2 并行策略（优先可比性，再提速）

| 场景 | 建议题目并发 | 是否可与另一条路线同时运行 | 评分并发 | 说明 |
|---|---:|---|---:|---|
| 新配置冒烟（10 题） | 1 | 不建议 | 1 | 先验证输出、checkpoint、路由 trace |
| A 路线 Semantic30 | 1；确认稳定后可升 2 | 可与 B 路线各 1 并发同时跑 | 评分单独串行 | PageIndex OFF 仍大量使用 LLM，先守住总并发 2 |
| B 路线定向 30/50 | 1；确认稳定后可升 2 | 可与 A 路线各 1 并发同时跑 | 评分单独串行 | 两路线必须不同 output/cache |
| 单个 50/100 回归 | 2；稳定后可升 4 | 不与另一个 pipeline 并行 | 评分在生成结束后运行 | 已验证的 500 基线使用过 4 |
| 单个 500 正式评测 | 4 | 不与任何 pipeline 或评分并行 | 生成完成后单独评分 | 降低服务争用和断点续跑复杂度 |

启动并发 2 后，连续观察至少 20 题：LLM 429/timeout、重试次数、每题耗时、checkpoint 是否连续、答案数是否等于已完成题数。若出现失败，不提升并发；先恢复到 1 并排查。`question_parallelism` 只影响吞吐，不应改变 run 的评测身份；但并发会影响服务排队与随机性，所以关键结果应同日复跑确认。2–5 个百分点的差异不可视为可靠收益，除非重复验证。

### 6.3 断点续跑与监控

- 仅在同一 `pipeline.name`、同一 YAML、同一 questions 文件和同一输出目录下使用 `resume: true`。
- 续跑前核验已完成 question IDs、`answers.jsonl` 行数、checkpoint 和运行日志；答案不完整时不要先评分。
- SSH/终端调用超时不代表远端任务停止；依次检查进程 PID、日志增长、已完成题数和输出时间戳。
- 若一次续跑的历史残留答案与当前配置不一致，应停止该 run、隔离/删除**仅该失败 run**的输出后重新开始；绝不可清理冻结的 500、AB50 或 S1 结果。

## 7. 新会话的推荐续接顺序

1. 阅读本文件，确认当前日期、服务可达性、以及没有遗留运行中的 pipeline。
2. 只读核验 BGE ES、manifest、LLM、reranker；不重建任何索引。
3. 读取 Semantic30 S1、AB50 ON 和 500 快照配置，建立新的实验命名与独立 cache/output。
4. 先执行 A0：为 S1 固定 30 题生成 raw-miss / rerank-drop / selector-drop / generation-gap 诊断表。
5. 同时可启动 B1 的 10 题冒烟，但总题目并发不超过 2；两路线的官方评分串行进行。
6. 每个单变量实验完成后，先看检索 trace 和按题型评分，再决定是否推进；无提升立即停止该支路。
7. 任何计划合流前，先向用户报告：变更、题集、指标差异、无效额外文档差异、回归风险与是否达到门槛。

## 8. 已淘汰/不可误用的结论

- 不把固定 50 的约 59 分外推为全量 500 水平；500 的 Semantic 125 题、Project 和 Completeness 分布不同。
- 不删除 PageIndex 来解决 Semantic；它在 AB50 带来 +14.17 综合分。
- 不使用 Conan/Qwen 的高维或 overlap 作为“天然更优”的依据；已有 50/100 对照均落后 BGE。
- 不关闭递归分区归并；Conan P0-1 已证明更差。
- 不采用 Semantic D1 文档硬选择、S3 anchor rescue、D2a 单纯扩大候选池；均无净收益或退化。
- 不使用不完整的 E5 索引或 D2b 输出。
- 不混用 `--no-correction` 与 correction 的得分，也不将 Lark 本地评分直接等同于公共榜单评分。

