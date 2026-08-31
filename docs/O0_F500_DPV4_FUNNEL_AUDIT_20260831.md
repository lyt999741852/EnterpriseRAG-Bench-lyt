# O0：F500-DPV4 全量错误漏斗复核（2026-08-31）

## 范围与方法

- **范围**：F500-DPV4 `no-correction`，500/500 题；读取既有 `answers.jsonl`、`route_trace.jsonl`、官方 `results.json` 和 EnterpriseRAG 语料。
- **方法**：使用官方 `expected_doc_ids` 与 `answer_facts` 做离线文档级阶段对齐，统计 `raw_views → pre_rerank → post_rerank → final_before_generation → submitted` 的首次丢失层。
- **注意**：事实匹配是词法支持探针，不是语义蕴含判定；`high_level` 与 `info_not_found` 因官方没有目标文档，不应把 `raw_miss` 桶直接解释为检索失败。
- **远端产物**：`/opt/enterprise-rag-bench/app/outputs/pageindex_full500_bge_dpv4_20260831/o0_funnel.json`

## 题目级漏斗

| 首个问题级失败桶 | 数量 | 占比 |
|---|---:|---:|
| fully_successful | 201 | 40.20% |
| generation_or_fact_coverage_gap | 113 | 22.60% |
| pageindex_or_selector_drop | 52 | 10.40% |
| citation_or_selector_drop | 25 | 5.00% |
| rerank_drop | 33 | 6.60% |
| raw_miss（含无目标文档题） | 76 | 15.20% |

剔除 `high_level` 10 题和 `info_not_found` 20 题后，具备目标文档的有效 raw-miss 为 **46 题**，主要集中在 Semantic（35 题）；这验证了 raw-miss 是真实检索瓶颈，但不是全部错误来源。

## 按题型分层

| 题型 | 数量/正确 | raw-miss | rerank drop | PageIndex/selector | citation/selector | generation/fact gap | fully successful |
|---|---:|---:|---:|---:|---:|---:|---:|
| basic | 175 / 134 | 8 | 9 | 19 | 4 | 23 | 112 |
| semantic | 125 / 51 | **35** | **20** | **20** | 4 | 12 | 34 |
| intra_document_reasoning | 40 / 23 | 1 | 2 | 6 | 1 | 10 | 20 |
| project_related | 40 / 23 | 0 | 0 | 1 | **5** | **32** | 2 |
| constrained | 30 / 20 | 0 | 0 | 3 | 3 | 14 | 10 |
| conflicting_info | 20 / 11 | 0 | 0 | 1 | 4 | 12 | 3 |
| completeness | 20 / 9 | 2 | 2 | 1 | 3 | 9 | 3 |
| miscellaneous | 20 / 18 | 0 | 0 | 1 | 1 | 1 | 17 |
| high_level | 10 / 5 | 10* | 0 | 0 | 0 | 0 | 0 |
| info_not_found | 20 / 20 | 20* | 0 | 0 | 0 | 0 | 0 |

`*` 表示无 `expected_doc_ids` 的官方题型，不纳入有效 raw-miss 优化分母。

## 事实级阶段损失

全量事实首次损失计数：

- `raw_views`：140
- `pre_rerank`：102
- `post_rerank`：48
- `final_before_generation`：275
- `submitted`：140
- `answer_generation`：1398
- 目标文档无词法支持：274
- 官方目标文档缺失/不适用：50

这表明：即使目标事实所在文档进入了早期候选，PageIndex/selector/final evidence 仍有明显损失；不能只扩大候选池。Project-related 的主要损失在最终证据覆盖与生成完整性，Semantic 则同时存在 raw、rerank 和 selector 三层损失。

## O0 结论与下一步

1. **首要检索目标是 Semantic 的 35 个有效 raw-miss**，先做通用候选覆盖和 embedding/索引 Recall@30/120/240/1000 对照，不先改生成 prompt。
2. **第二目标是 Semantic 的 rerank/selector 损失**：20 个问题在 rerank 阶段丢失、20 个问题在 PageIndex/selector 阶段丢失；候选进入后要验证文档多样性和证据 admission，而非继续盲目扩大 `candidate_k`。
3. **Project-related 不宜只做 raw-miss 方案**：问题级 raw-miss 为 0，但 generation/fact gap 为 32/40，需针对多文档/项目范围覆盖和提交证据做 O4/O5 诊断。
4. **Completeness 同时有检索和生成缺口**：先保证多分面候选不被截断，再验证生成逐分面覆盖。
5. **Conflicting_info、Intra-document、Constrained** 主要是证据选择/生成层问题；保持当前通用检索托底，避免影响 Basic、Miscellaneous、InfoNotFound 控制题。
6. `high_level` 的 recall=0 与 `info_not_found` 的 raw-miss 是官方目标文档定义导致的统计现象，不能据此启动 embedding 重建。

因此 O1 应保持“原始 BM25+dense 永远保留、附加视图只能追加”的通用托底；之后再分别进行低置信度 shadow query 和替代 embedding 的只读召回筛选。
