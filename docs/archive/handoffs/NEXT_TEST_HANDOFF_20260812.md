# EnterpriseRAG 后续测试交接（Qwen3 Embedding v2）

> **历史状态说明（2026-08-13）：本交接已完成并停止执行。** Q3-A/Q3-B
> 已完成，Qwen3/Conan 端到端结果显著低于 BGE；当前主线已回退至
> BGE-small + remote rerank。最新入口见根目录 `CURRENT_STATUS.md`，本文件
> 仅作为 Qwen3 测试过程和参数记录保留。

> 日期：2026-08-12（Asia/Shanghai）  
> 新会话入口：先读本文件，再读 `../ledgers/RAG_TEST_RECORD_THROUGH_20260812.md`；历史细节见根目录 `OPTIMIZATION_TRACE.md`。

## 1. 当前决策

- 历史版本已确认是 **V5.2**：10 题锚点 90% correctness / 77.33 combined；50 题分层 58% correctness / 54.41 combined。
- 旧 BGE 库近期最佳 50 题为 **BGE + remote rerank**：62.0% correctness、66.49% completeness、58.74 combined、66.19% recall、0.17 extra。
- 当前代码包含多轮实验能力，但后续新库首次测试应控制变量：先切换 embedding/index，保留已验证主链；不要同时启用多视图、semantic evidence quota 或选择性 PageIndex。
- 新库通过 50 题前，不删除 BGE 旧索引及历史输出。

## 2. 新向量资源（用户确认）

| 项 | 值 |
|---|---|
| 本地原始语料 | `D:\EnterpriseRAG-Bench\corpus\all_documents` |
| 服务器语料 | `/opt/enterprise-rag-bench/app/corpus/all_documents` |
| 测评问题 | `D:\EnterpriseRAG-Bench\questions.jsonl`（服务器对应 app 根目录） |
| 切块/文档缓存 | `.index_cache/full_es_qwen3_emb` |
| 预处理规模 | 511,957 个源文档；1,075,100 个原始 chunks |
| 切块 | `hierarchical-v1-448`；448 tokens；overlap 32 |
| Embedding API | `http://10.72.55.209:7993/v1` |
| 模型名/维度 | `embedding` / 1792 |
| API Key | 只通过环境变量 `EMBEDDING_API_KEY`；禁止写入配置和文档 |
| Elasticsearch | `http://10.72.100.29:31920`，ES 7.17.8 |
| 目标索引 | `enterprise-rag-qwen3-emb-v2` |
| 检索别名 | `enterprise-rag-qwen3-emb` |
| 当前报告规模 | 3,084,120 条向量记录，约 110.3 GB |
| 密集检索模式 | **必须 `dense_mode: script_score`；禁止原生 knn** |
| 推荐配置 | `configs/eval_pageindex_balanced50_q3emb.yaml` |

## 3. 启动测试前的强制预检

### 3.1 先处理索引计数异常

报告的索引记录 3,084,120，而缓存只有 1,075,100 chunks，约 2.87 倍。不得仅因 `_count` 大于 chunks 就判定构建成功。需只读核验：

1. alias `enterprise-rag-qwen3-emb` 实际指向哪些索引；
2. mapping 中 `embedding` 维度是否 1792；
3. ES 版本确为 7.17.8，配置确为 `script_score`；
4. 抽样/聚合确认 `chunk_id` 是否重复，是否混入多次构建或旧 chunk 版本；
5. 随机取若干 cache `chunk_id` 用 `_mget` 检查存在性、source 字段与 embedding_model；
6. 检查索引健康、分片数、docs.deleted、store size；
7. alias 不得同时覆盖旧版本索引。

若一条 chunk 对应多条向量记录，先定位原因；不要贸然删除或重建索引。

### 3.2 配置预检

`configs/eval_pageindex_balanced50_q3emb.yaml` 当前已经设置新 corpus/cache/index、1792 维和 `script_score`，但历史版本中 `retrieval.reranker.enabled` 为 false。首次新库测试建议分两轮：

- Q3-A（单变量向量库切换）：按推荐配置原样跑，和 V5.2/P1 50 题比较，回答“新 embedding + 新切块本身如何”。
- Q3-B（当前主链）：复制为独立配置，启用已验证 remote reranker，candidate 120、top_n 30；其余不变，和旧 BGE rerank 58.74 combined 比较。

两轮必须使用不同 `pipeline.name` 和 PageIndex `cache_dir`，禁止 resume 串用。

## 4. 推荐执行顺序

1. 读取 `CURRENT_STATUS.md`、本文件、测试总记录。
2. 只读核验服务器进程、ES alias/mapping/count/health、缓存 metadata。
3. 本地解析推荐 YAML，确认 50 题题型比例仍为 18/12/4/4/3/2/2/2/2/1。
4. 运行 2～3 个代表题冒烟（basic、semantic、conflicting 各 1），确认 script_score、PageIndex、LLM、引用链均正常。
5. 运行 Q3-A 50 题；保存完整产物；用官方评分器评分。
6. 运行 Q3-B 50 题（启用 reranker）；保存独立产物并评分。
7. 对比四条基线：V5.2 50、P1 50、BGE rerank 50、Q3-A/Q3-B。
8. 只有新库 50 题稳定且索引唯一性确认后，才考虑 500 题正式评测。

## 5. 推荐主链和禁用项

首次 Qwen3 新库 A/B 的共同链路：

`原问题 hybrid(BM25+dense,RRF) → （Q3-B 才启用 rerank）→ EvidencePlanner 题型路由 → PageIndex 文档树/节点审计/缺口多跳 → Generator 证据选择/事实核验/最终审计`

首次测试禁止同时启用：

- `multi_view.enabled=true`；
- `semantic_evidence_quota.enabled=true`；
- `pageindex.enabled_types` 外部选择性绕过；
- basic 查询改写与权重调整；
- 任何新 prompt。

这些变量应等 Q3-A/Q3-B 建立新库基线后单独做 A/B。

## 6. 可复现性和运行规则

- 生成流程使用服务器 embedding 环境；官方评分使用 `/opt/enterprise-rag-bench/official_eval_venv/bin/python` 或已验证 base 环境。
- LLM endpoint/model 保持现有 Lark 配置，temperature 0，thinking false。
- 问题并发推荐 4；官方评分并发 4。并发参数不应进入 run fingerprint。
- `resume=true` 仅可用于同 fingerprint、同 pipeline 输出；配置改变必须新建输出目录。
- 后台进程使用 `setsid`；SSH 包装器等待超时不代表子进程失败，启动后必须以 `ps`、日志和 checkpoint 三者确认。
- API Key 仅通过环境变量传入，日志与交接文档不得出现明文。

## 7. 当前优先调优候选（新库基线完成后）

1. basic 三组单变量权重消融：0.7/0.3；1/1；1/1/0.35 改写。
2. semantic：在 PageIndex 内保存 facet 到候选文档/节点的独立归属，而不是在 PageIndex 前做 RRF。
3. PageIndex 性能：统计树缓存命中、规划/选择/审计 LLM 次数、每题 hop 数和 route action；不要只看总时长。
4. qst_0432 限定词完整性、qst_0480 跨文档组织综合、qst_0416 版本配对仍是历史重点。

## 8. 关键文件

- 当前入口：`CURRENT_STATUS.md`
- 测试总记录：`docs/archive/ledgers/RAG_TEST_RECORD_THROUGH_20260812.md`
- 本交接：`docs/archive/handoffs/NEXT_TEST_HANDOFF_20260812.md`
- 历史全追溯：`OPTIMIZATION_TRACE.md`
- 原向量重构交接：`docs/archive/VECTOR_REBUILD_HANDOFF.md`（部分规模/状态已过时，以本文件为准）
- 新库推荐配置：`configs/eval_pageindex_balanced50_q3emb.yaml`
- 新库构建配置：`configs/full_es_qwen3_emb.yaml`
- 旧 BGE 近期最佳：`configs/eval_pageindex_balanced50_bge_rerank_cpu.yaml`
