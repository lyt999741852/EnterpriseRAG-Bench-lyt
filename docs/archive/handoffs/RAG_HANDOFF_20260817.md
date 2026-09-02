# EnterpriseRAG-Bench 当前 RAG 交接（历史）

> **此文件的状态截止于 2026-08-17，后续实验已发生变化。新会话请优先阅读 [`RAG_HANDOFF_20260825.md`](RAG_HANDOFF_20260825.md)。**

> 更新时间：2026-08-17（Asia/Shanghai）  
> 本文件是新会话的当前状态入口。BGE 基线和 V3 数据集均已隔离保存。

## 1. 当前结论

- 当前可靠回退线：BGE-small + remote rerank。
- 新数据线：Conan448/32 overlap + 1792维 embedding + V3 ES index。
- V3 数据完整性已通过核验，但同一 RAG 架构下的100题表现低于 BGE。
- V3 P0-1（仅关闭递归 `__pN` 归并）已完成并且更差，暂不采纳。
- 下一步是 V3 P0-2：只扩大 hybrid 和 rerank 候选池。
- 暂不跑500题，先完成各个V3参数变体的100题 pipeline + 官方 no-correction 评测。

## 2. 评测协议

当前A/B结果统一使用官方 `metrics_based_eval`：

- 100题同一题目集合
- question-only 输入
- Lark/Qwen3.5-27B-AWQ 作为评测模型
- `--no-correction`
- 评测阶段不使用 GPT

当前结果不是官方默认 correction 模式。最终提交前才需要准备 isolated correction bundle，并分别确认 correction/no-correction 结果；两种模式的分数不得直接混比。

## 3. BGE 最佳基线（不可修改）

### BGE P0 100题

配置：`configs/eval_pageindex_stratified100_bge_rerank_question_only_llm_route_multiview_p0_20260814.yaml`

官方 no-correction 结果：

| Correctness | Completeness | Combined | Recall | Invalid Extra |
|---:|---:|---:|---:|---:|
| 63.0% | 65.70% | 58.83 | 61.00% | 0.17 |

输出：
`/opt/enterprise-rag-bench/app/outputs/pageindex_stratified100_bge_rerank_question_only_llm_route_multiview_p0_20260814`

### BGE 50题最佳记录

配置：`configs/eval_pageindex_balanced50_bge_rerank_cpu.yaml`

结果：Correctness 62.0%、Completeness 66.49%、Combined 58.74、Recall 66.19%、Invalid Extra 0.17。

更早的历史记录：V5.2 10题 90.0/77.33/77.33、V5.2 50题 58.0/59.21/54.41、P1 50题 60.0/59.19/54.66。这些只用于追溯，不与100题绝对横比。

## 4. 当前 RAG 主链路

```text
question-only
 -> LLM inferred retrieval route
 -> BM25 + dense + RRF
 -> query rewrite / answer intent / multi-view
 -> remote rerank
 -> PageIndex candidate/node audit
 -> precision_v3 evidence selection
 -> fact verification
 -> final answer audit
```

真实 benchmark `question_type` 不直接暴露给系统；当前路由来自问题文本的 LLM inference。ES 检索必须使用 `dense_mode: script_score`，因为目标 ES 是7.17.8。`parent_expansion.enabled` 当前必须保持 false，ES backend 尚未支持该扩展。

核心代码：`src/pipeline.py`、`src/elasticsearch_backend.py`、`src/pageindex_router.py`、`src/generator.py`、`src/embedder.py`。

## 5. V3/Conan 数据集

本地缓存：
`D:\EnterpriseRAG-Bench\.index_cache\full_es_qwen3_emb_v3_conan448\`

服务器缓存：
`/opt/enterprise-rag-bench/app/.index_cache/full_es_qwen3_emb_v3_conan448/`

- `chunks.jsonl`：3,030,317行，约3.5GB
- manifest：`preprocess_complete`
- `_meta.json`：511,957 source docs、3,030,317 chunks、failed_files=0
- Conan recursive chunk：448 tokens，overlap32，embedding service window 512
- embedding：`http://10.72.55.209:7993/v1`，model `embedding`，1792维
- rerank：`http://10.72.55.209:7992/v1/rerank`，bge-reranker-v2-m3
- LLM：`http://10.72.100.35:7777/v1`，model `lark`
- API key 只能通过 `EMBEDDING_API_KEY`、`LARK_API_KEY` 环境变量传入，不写入配置或日志

ES：

- URL：`http://10.72.100.29:31920`
- index：`enterprise-rag-qwen3-emb-v3-conan448`
- alias：`enterprise-rag-qwen3-emb-v3`
- count：3,030,317；deleted=0；16 primary shards；green；unassigned=0
- mapping：`embedding` dense_vector 1792维，`chunk_id` keyword，`embedding_model` keyword
- alias 只指向 V3 index

缓存 chunks、manifest 元数据和 ES count 已完成一致性核验。`__pN` 是 Conan 512-token 限制下对当前基础 chunk 的合法递归分片，不是旧数据混入；去除任意层 `__pN` 后可以追溯到当前基础 chunk。

## 6. V3 已完成结果

### V3 P0 原始同架构基线

配置：`configs/eval_pageindex_stratified100_qwen3_v3_p0_chain_20260816.yaml`

输出：`/opt/enterprise-rag-bench/app/outputs/pageindex_stratified100_qwen3_v3_p0_chain_20260816`

| Correctness | Completeness | Combined | Recall | Invalid Extra |
|---:|---:|---:|---:|---:|
| 53.0% | 56.56% | 48.42 | 53.11% | 0.18 |

### V3 P0-1：关闭递归片段归并

配置：`configs/eval_pageindex_stratified100_qwen3_v3_p0_r1_nocollapse_20260817.yaml`

唯一检索变化：

```yaml
retrieval:
  collapse_recursive_partitions: false
```

输出：`/opt/enterprise-rag-bench/app/outputs/pageindex_stratified100_qwen3_v3_p0_r1_nocollapse_20260817`

pipeline 和官方评测均已完成100题，`completed_questions=100`、`skipped_rows=0`、`num_corrected_questions=0`。

| 指标 | V3 P0 | V3 P0-1 |
|---|---:|---:|
| Correctness | 53.0% | 52.0% |
| Completeness | 56.56% | 55.14% |
| Combined | 48.42 | 47.42 |
| Recall | 53.11% | 50.98% |
| Invalid Extra | 0.18 | 0.18 |

结论：关闭递归归并没有改善，R1 不作为新基线，但配置和结果必须保留。

## 7. 当前问题定位

### 7.1 主要是召回和证据覆盖下降

V3 的 Invalid Extra 0.18 与 BGE 0.17 基本持平，说明不是噪声文档大量增加，而是正确证据没有进入最终上下文。V3 P0 相比 BGE P0 的 Recall 是53.11%对61.0%。

V3退化明显的题型：

- Basic：Recall 65.71%，低于BGE 80.0%
- Project Related：Recall 30.55%，低于BGE 42.36%
- Conflicting Info：Recall 0%，BGE为37.5%
- Semantic：Recall 36%，但正确率仅28%，说明部分题虽召回文档，具体事实仍被证据选择丢掉

### 7.2 路由是结构性弱点，但不是V3独有回归

V3 route trace：Semantic 14/25正确，Project Related 5/8正确，Conflicting Info 0/4正确，Completeness 3/4正确。Conflicting Info 4题被误判为 basic/constrained。

BGE 路由混淆情况基本相同，所以路由需要后续优化，但不能单独解释 V3 相对 BGE 的下降。V3 的向量排序和更高片段密度使误路由的影响更严重。

### 7.3 证据选择过于保守

当前 `evidence_selection_candidate_chunks=24`、`max_chunks=10`、`max_context_chunks=10`、`max_chunks_per_doc=4`、`fail_closed=true`。这能保持低 Invalid Extra，但会漏掉日期、数字、版本号、阈值和 ticket ID，并在证据不完整时直接拒答。

## 8. 后续逐步优化计划

每个变体都必须使用新的 YAML、`pipeline.name`、output 目录和 PageIndex `cache_dir`；不得修改BGE文件、索引或结果，也不得与其他参数实验并发。

### P0-2（下一步）：扩大候选池

只改：

```yaml
retrieval:
  candidate_k: 480
  reranker:
    candidate_k: 240
    top_n: 30
```

其他参数恢复/保持 V3 P0 基线（包括 `collapse_recursive_partitions: true`）。完成100题 pipeline 后，运行官方 no-correction 评测。

### P0-3：dense/BM25 权重校准

在P0-2之后，固定其他参数，分别测试 `dense_weight=0.15/0.30/0.50`。不要同时改 query rewrite、PageIndex 或 evidence selection。

### P1-1：扩大 PageIndex 多文档预算

只在V3中测试：

```yaml
pageindex:
  max_candidate_documents: 40
  mode_budgets:
    project_related:
      estimated_documents: 4
      candidate_documents: 36
      max_selected_nodes: 20
      max_hops: 2
    completeness:
      estimated_documents: 8
      candidate_documents: 40
      max_selected_nodes: 32
      max_hops: 2
```

### P1-2：增加自适应 evidence budget

```yaml
generation:
  adaptive_type_budgets:
    project_related:
      candidate_chunks: 32
      max_chunks: 14
      max_chunks_per_doc: 4
    completeness:
      candidate_chunks: 40
      max_chunks: 16
      max_chunks_per_doc: 4
    semantic:
      candidate_chunks: 32
      max_chunks: 12
      max_chunks_per_doc: 4
```

先保持 `evidence_selection_fail_closed=true`；只有证据预算实验完成后，才单独测试 fail-open。

### P1-3：fail-closed 对照（后续）

单独测试 `fail_closed=false`、`fallback_chunks=2`、`anchor_chunks=1`，观察 Correctness/Completeness 是否提升以及 Invalid Extra 是否恶化。

### P2：检索需求路由（最后）

如果参数微调仍无法恢复 Conflicting Info，再调整LLM输出的检索需求抽象：`single_fact`、`multi_document`、`conflict_or_version_sensitive`、`exhaustive_collection`、`intra_document_reasoning`。不能直接把 benchmark 的真实题型传给系统。这属于路由逻辑调整，不应与P0参数实验混合。

## 9. 执行与回退规则

- 所有V3实验使用 `read_existing_index: true`，禁止重建3M文档索引。
- 每个变体先跑100题 pipeline，再跑同一官方 no-correction 评测；未稳定前不跑500题。
- SSH命令超时不等于子进程失败，必须检查 PID、日志、答案数和结果文件。
- BGE回退配置：`configs/eval_pageindex_stratified100_bge_rerank_question_only_llm_route_multiview_p0_20260814.yaml`。
- 不要通过恢复或覆盖V3文件来切回BGE；两条实验线完全独立。
- 新会话首读本文件，然后读取对应配置和 `V3_DATASET_HANDOFF_20260816.md`。

下一项可直接执行：创建并运行 V3 P0-2（`candidate_k=480`、rerank `candidate_k=240`）100题 pipeline，完成后运行官方评测并与 V3 P0、P0-1、BGE P0 对比。
