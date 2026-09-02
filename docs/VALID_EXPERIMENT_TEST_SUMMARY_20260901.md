# EnterpriseRAG 有效实验测试记录（汇报版）

生成日期：2026-09-02（Asia/Shanghai）  
纳入范围：已完成端到端评分、题量不少于 50 的实验。除特别标注外，评分均来自官方 `metrics_based_eval`。

> 本文按“哪些结论可以用于决策”组织，而不是按日期罗列日志。50 题结果用于定位设计因素；500 题结果用于代表全量能力。不同题集、不同生成模型或不同 judge 的分数不能直接排序。

## 1. 一页结论（可直接放汇报首页）

### 当前架构与全量参考线

当前主线是：**BGE-small 向量检索 + hybrid RRF + remote reranker + 题型路由的 PageIndex + 证据约束生成**。

| 全量版本 | 题数 | 生成 / Judge | Correctness | Completeness | 综合分 | 文档召回 | 无效额外文档 |
|---|---:|---|---:|---:|---:|---:|---:|
| 冻结基线 F500 | 500 | Qwen3.5-27B（lark）/ 同模型 | 60.60% | 62.57% | 55.18 | 61.12% | 0.18 |
| 当前 F500 参考线 | 500 | DeepSeek-V4-Flash / 同模型 | **62.80%** | **64.25%** | **57.01** | 60.29% | 0.23 |

DPV4 这一端到端组合相对 Qwen/Lark 冻结版高 `+2.20pp` correctness、`+1.68pp` completeness、`+1.83` 综合分；但生成器、改写/路由 LLM 与 judge 同时变化，因此只能描述为**端到端组合结果提升**，不能归因于某一个模型或模块。

### 已有可靠实验结论

1. **remote reranker 是已验证的保留项。** 同一套分层 50 题、仅增加 reranker，综合分从 54.66 提升到 58.74，文档召回从 58.39% 提升到 66.19%。
2. **BGE 是当前主线向量方案。** 两轮 Conan/Qwen 试验未建立优于 BGE 的证据；Conan448 的 50 题 correctness 持平，但文档召回低 5.61pp。
3. **不应全量增加多视图，也不应绕过 PageIndex。** 前者在同题对照中回退，后者出现显著回退。
4. **O4.P3 等高分 50 题方案仍是候选，不是已合流结论。** 它们依赖 DPV4 自评或未独立复验，必须经固定独立 judge 与 F500 复验。

---

## 2. 统一的测试口径与固定底座

### 指标说明

| 指标 | 含义 | 汇报时应怎样解释 |
|---|---|---|
| correctness | 答案是否正确 | 最主要的答案质量指标 |
| completeness | 答案是否覆盖要求的信息 | 适合观察多约束、多跳和穷举题 |
| combined | 官方综合分 | 同题集、同 judge 内才可横比 |
| document recall | 是否召回标注的证据文档 | 仅有 `expected_doc_ids` 的题目有意义 |
| invalid extra docs | 平均无效额外引用文档数 | 越低越好，但不能脱离 correctness 单独追求 |

High-level 和 Info-not-found 通常不配置 `expected_doc_ids`；其 `document recall = 0` 不是检索失败，不应纳入“有 gold 文档题”的召回解释。

### BGE 主线的固定检索底座

| 项目 | 固定值 |
|---|---|
| 语料 | EnterpriseRAG 全量语料，511,957 个唯一文档 |
| Elasticsearch 索引 | `enterprise-rag-bge-small-v1` |
| embedding | `BAAI/bge-small-en-v1.5`，384 维，cosine |
| 切块 | `fixed-v2`，512 tokens、overlap 0 |
| 向量 chunks | 928,534 |
| 主线检索 | BM25 + dense 的 hybrid RRF；`candidate_k=240` |
| 主线精排 | remote reranker，候选 120 → 返回 30 |

---

## 3. 全量评测：代表系统真实能力的两条 F500 参考线

### 实验 F500-Qwen：冻结、无 correction 的 Qwen/Lark 基线

**目的**：固定 BGE RAG 架构，建立可回溯的 500 题 Qwen 基准。  
**题型构成**：Basic 175、Semantic 125、Intra-document reasoning 40、Project-related 40、Constrained 30、Conflicting info 20、Completeness 20、Miscellaneous 20、High-level 10、Info-not-found 20。  
**模型搭配**：Qwen3.5-27B（lark）生成 / Qwen3.5-27B（lark）评分 / BGE-small 384d / remote reranker（120 → 30）。  
**检索和生成设置**：question-only、hybrid RRF、多视图、题型路由 PageIndex、无 parent expansion；官方 `--no-correction`。

| 题型 | 题数 | Correctness | Completeness | 综合分 | 文档召回 | 无效额外文档 |
|---|---:|---:|---:|---:|---:|---:|
| Basic | 175 | 68.57% | 67.92% | 64.40 | 71.43% | 0.11 |
| Semantic | 125 | 42.40% | 41.21% | 38.10 | 42.40% | 0.29 |
| Intra-document reasoning | 40 | 72.50% | 82.23% | 70.42 | 90.00% | 0.07 |
| Project-related | 40 | 37.50% | 46.74% | 25.87 | 41.87% | 0.35 |
| Constrained | 30 | 70.00% | 85.09% | 66.89 | 78.33% | 0.03 |
| Conflicting info | 20 | 70.00% | 69.06% | 60.09 | 37.50% | 0.05 |
| Completeness | 20 | 45.00% | 37.66% | 25.83 | 32.57% | 0.55 |
| Miscellaneous | 20 | 95.00% | 84.00% | 84.00 | 95.00% | 0.00 |
| High-level | 10 | 40.00% | 72.17% | 40.00 | 0.00%* | 0.00 |
| Info-not-found | 20 | 95.00% | 100.00% | 95.00 | 0.00%* | 0.00 |
| **总计** | **500** | **60.60%** | **62.57%** | **55.18** | **61.12%** | **0.18** |

**可用于汇报的结论**：该版本是 Qwen/Lark 下的冻结全量基线。最主要短板为 Project-related、Completeness 和 Semantic；Intra-document reasoning 与 Constrained 表现较强。

### 实验 F500-DPV4：当前端到端全量参考线

**目的**：在同一 500 题、同一 BGE 索引和相同主干检索架构下，验证 DPV4 端到端组合。  
**与 F500-Qwen 的主要差异**：生成、query rewrite、题型路由以及 judge 使用 DeepSeek-V4-Flash；BGE 索引、chunk、hybrid RRF、reranker 和 PageIndex 主架构保持一致。  
**模型搭配**：DeepSeek-V4-Flash 生成 / DeepSeek-V4-Flash 评分 / BGE-small 384d / remote reranker。  
**运行状态**：500/500 完成，0 skipped，官方 `--no-correction`。

| 题型 | 题数 | Correctness | Completeness | 综合分 | 文档召回 |
|---|---:|---:|---:|---:|---:|
| Basic | 175 | 76.57% | 74.41% | 72.02 | 77.14% |
| Semantic | 125 | 40.80% | 44.37% | 36.42 | 40.00% |
| Intra-document reasoning | 40 | 57.50% | 68.63% | 55.83 | 77.50% |
| Project-related | 40 | 57.50% | 51.04% | 39.17 | 36.85% |
| Constrained | 30 | 66.67% | 77.30% | 59.29 | 73.33% |
| Conflicting info | 20 | 55.00% | 60.43% | 44.94 | 40.00% |
| Completeness | 20 | 45.00% | 45.08% | 33.06 | 23.03% |
| Miscellaneous | 20 | 90.00% | 88.75% | 88.75 | 90.00% |
| High-level | 10 | 50.00% | 56.67% | 43.33 | 0.00%* |
| Info-not-found | 20 | 100.00% | 100.00% | 100.00 | 0.00%* |
| **总计** | **500** | **62.80%** | **64.25%** | **57.01** | **60.29%** |

**可用于汇报的结论**：这是当前最具代表性的系统全量结果。Project-related、Semantic、Completeness 仍是应优先优化的三类题型。

---

## 4. 同题 50 题对照：已经验证的架构决策

以下各项均来自相同的“分层 50 题”题集：Basic 18、Semantic 12、Intra-document reasoning 4、Project-related 4、Constrained 3、Conflicting info 2、Completeness 2、Miscellaneous 2、High-level 1、Info-not-found 2。除特别说明外，生成和 judge 均为 Qwen3.5-27B（lark），向量均为 BGE-small 384d。

### 实验 A：remote reranker 的净价值

**问题**：在 BGE + PageIndex 架构中，精排是否带来可重复的端到端收益？  
**对照方式**：同题集、同生成模型、同 BGE 索引、同 PageIndex 按题型路由；唯一主要变量为是否启用 remote reranker。

| 版本 | Correctness | Completeness | 综合分 | 文档召回 | 无效额外文档 |
|---|---:|---:|---:|---:|---:|
| 无 rerank | 58.0% | 58.43% | 54.66 | 58.39% | 0.26 |
| remote rerank | **62.0%** | **66.49%** | **58.74** | **66.19%** | **0.17** |
| 变化 | `+4.0pp` | `+8.06pp` | `+4.08` | `+7.80pp` | `-0.09` |

**结论**：这是最干净的同题 A/B 证据，remote reranker 应保留。

### 实验 B：不加区分地扩充多视图会稀释强信号

**问题**：是否把多视图候选扩展到全部题型？  
**变化**：在已经启用 remote reranker 的 BGE 主线之上，增加“全题型多视图”候选；其他底座不变。

| 版本 | Correctness | Completeness | 综合分 | 文档召回 | 无效额外文档 |
|---|---:|---:|---:|---:|---:|
| rerank 基线 | 62.0% | 66.49% | 58.74 | 66.19% | 0.17 |
| 全题型多视图 + rerank | 60.0% | 60.96% | 56.41 | 61.94% | 0.13 |

**结论**：更多改写/多路候选并不天然更好；该策略降低了强匹配 chunk 的排序优势，因此未采用为默认配置。

### 实验 C：绕过 PageIndex 的风险

**问题**：是否对一部分题型跳过 PageIndex，以降低 LLM 选择开销？  
**变化**：在 remote reranker BGE 主线上，对部分题型选择性绕过 PageIndex。

| 版本 | Correctness | Completeness | 综合分 | 文档召回 | 无效额外文档 |
|---|---:|---:|---:|---:|---:|
| rerank 基线 | 62.0% | 66.49% | 58.74 | 66.19% | 0.17 |
| 选择性绕过 PageIndex | 32.0% | 40.39% | 31.67 | 39.18% | 0.21 |

**结论**：当前实现中，简单地关闭 PageIndex 会破坏证据组织与后续生成链路，不能作为降本策略。

### 实验 D：partial-open 证据解析器

**问题**：证据准入不完整时，是否允许保留已覆盖的一部分证据？  
**变化**：相对 V5.2 分层 50，唯一变量为 partial-open evidence parser。

| 版本 | Correctness | Completeness | 综合分 | 文档召回 | 无效额外文档 |
|---|---:|---:|---:|---:|---:|
| V5.2 分层基线 | 58.0% | 59.21% | 54.41 | 61.70% | 0.15 |
| P1 partial-open | 60.0% | 59.19% | 54.66 | 59.81% | 0.19 |

**结论**：综合分仅 `+0.25`，可作为容错机制保留，但不是决定性增益来源。

---

## 5. 向量数据集方案：BGE 与 Conan 的比较

### 实验 E：早期 Qwen/Conan 方案

**目的**：验证 Qwen embedding 与 Conan 切块方案能否替代 BGE。  
**数据设置**：Qwen embedding，1792 维；Conan 512-token 递归分区；1,075,100 基础 chunks、3,084,120 物理向量记录。  
**限制**：该批 50 题未保留题型分布，不能与分层 50 的题型表现作细粒度比较。

| 版本 | reranker | Correctness | Completeness | 综合分 | 文档召回 | 无效额外文档 |
|---|---|---:|---:|---:|---:|---:|
| Q3-A：Qwen/Conan | 无 | 42.0% | 43.64% | 37.41 | 40.78% | 0.23 |
| Q3-B：Qwen/Conan | remote reranker | 40.0% | 40.05% | 36.41 | 43.85% | 0.15 |

**结论**：早期 Conan 方案显著弱于同期 BGE，reranker 也未能补救；不作为主线。

### 实验 F：Conan448 与 BGE 的 DPV4 对照

**目的**：在同一分层 50 与 DPV4 环境中，比较新的 Conan448 数据构建与 BGE 主线。  
**Conan448 设置**：ES 索引 `enterprise-rag-qwen3-emb-v3-conan448`；OpenAI-compatible embedding，1792 维；`langchain_conan_recursive`，448 tokens / overlap 32；3,030,317 向量记录；remote reranker 120 → 30。  
**BGE 对照**：同一题集、同 DPV4 生成和评分、同 remote reranker，采用 BGE `fixed-v2` 512/0。

| 向量方案 | Correctness | Completeness | 综合分 | 文档召回 | 无效额外文档 |
|---|---:|---:|---:|---:|---:|
| BGE + DPV4 | 68.0% | **71.37%** | 62.13 | **70.39%** | 0.17 |
| Conan448 + DPV4 | 68.0% | 68.06% | **62.89** | 64.78% | **0.13** |

**结论**：Conan448 的综合分略高 `+0.76`，但 correctness 持平、document recall 低 `5.61pp`，且索引规模显著更大。现阶段没有足够证据值得替换 BGE 主线。

---

## 6. 候选优化：可以展示，但必须标明“未完成独立放行”

### 实验 G：A3.5 conflict guard

**目的**：减少冲突题中旧方案、草案或未生效版本被当作最终事实的风险。  
**变化**：PageIndex selector contract + generation conflict guard；其余为 BGE + remote reranker + 分层 50。  
**结果**：correctness 64.0%，completeness 66.50%，综合分 59.41，document recall 63.89%，extra 0.19。相对冻结 50 题 rerank 基线，综合分 `+0.07`。

**结论**：满足小幅合流门槛，但收益存在生成波动；适合描述为“防回退约束”，不是单独的高分突破。

### 实验 H：O4.P3 软池与 selector 稳定化

**目的**：在 PageIndex 证据选择中为临界文档提供最多 `+2` 的软候选池，并放宽 fail-closed。  
**结果**：DPV4 judge 下，correctness 72.0%，completeness 72.28%，综合分 67.30，document recall 72.93%，extra 0.21。

**限制**：仅 DPV4 自评，且 conflicting_info 存在回退；尚未用固定独立 judge 与 F500 验证。

### 实验 I：O4.P3.4 conflict guard 双 judge

**目的**：验证冲突 guard 在不同 judge 下是否稳定。  
**结果**：同一答案在 DPV4 / Qwen-Lark judge 下，correctness 为 78.0% / 68.0%，completeness 为 76.11% / 68.61%，综合分为 71.20 / 59.68；document recall 76.12%，extra 0.21。

**结论**：冲突题控制通过，但两个 judge 的差异很大。汇报中应将其列为“候选方案经双 judge 发现评分敏感性”，而不是直接采用 DPV4 高分。

---

## 7. 早期 V2 召回保护：为何 50 题分数高、为何不应作为主基线

**实验设置**：2026-07-30，Qwen3.5-27B（lark）生成与评分，BGE-small 384d，无独立 reranker；BGE `fixed-v2` 512/0，928,534 chunks。  
**结果**：correctness 72.0%，completeness 75.87%，综合分 70.10，document recall 88.0%，extra 3.06。

**关键限制**：该测试只有 **Basic 50 题**，而 Basic 是单事实、词面清晰、通常单文档即可回答的题型；它不包含 Semantic、跨文档、冲突、穷举等困难题型。因此该分数是有效的 Basic 子集结果，但**不是官方全题型能力的估计，也不应和 F500 综合分比较**。

---

## 8. 汇报引用规则

| 想表达的结论 | 推荐引用 | 不应使用 |
|---|---|---|
| 当前系统总体能力 | F500-DPV4：综合分 57.01 | Basic 50 的 70.10 |
| Qwen 架构冻结基线 | F500-Qwen：综合分 55.18 | 未留题型构成的旧 Conan 50 |
| reranker 价值 | 同题 A/B：54.66 → 58.74 | 不同日期的非配对结果 |
| BGE vs Conan 的选型 | BGE/Conan448 同题 DPV4 对照，优先看 recall 与成本 | 只取 Conan 的 combined +0.76 |
| O4.P3 潜力 | 标记为候选、待独立 judge/F500 放行 | 把 DPV4 自评分作为最终结论 |

## 9. 原始材料与可追溯配置

- [历史总台账](archive/ledgers/RAG_TEST_RECORD_THROUGH_20260812.md) 与 [优化追溯](../OPTIMIZATION_TRACE.md)
- [A3.5 AB50](SEMANTIC_A3_5_GENERATION_CONFLICT_GUARD_AB50_20260826.md)
- [DPV4/BGE 50 题](DPV4_LLM_SWAP_BGE50_20260828.md) 与 [Conan448 对照](CONAN448_DPV4_BGE50_20260828.md)
- [O4.P3 AB50](O4P3_BALANCED50_NO_CORRECTION_20260831.md)、[O4.P3.4 双 judge](O4P34_CONFLICT_AB50_DUAL_JUDGE_20260831.md)
- [F500 DPV4 官方记录](F500_BGE_DPV4_NO_CORRECTION_20260831.md)
- [F500 Qwen 冻结配置](../configs/eval_pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817.yaml) 与 [架构说明](BGE_RAG_ARCHITECTURE_REPORT_20260820.md)
