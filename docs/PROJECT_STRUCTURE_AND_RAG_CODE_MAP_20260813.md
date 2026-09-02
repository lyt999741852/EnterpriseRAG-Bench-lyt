# EnterpriseRAG-Bench 目录与核心代码地图

更新时间：2026-08-13

## 当前主线

当前生产/优化回退点是 BGE-small 索引：

- 配置：`configs/eval_pageindex_balanced50_bge_rerank_cpu.yaml`
- 索引：`enterprise-rag-bge-small-v1`
- 切块：`fixed-v2`，512 个 whitespace token，overlap 0
- 检索：ES BM25 + BGE dense，RRF（dense weight 0.3）
- 重排：remote reranker，120 candidates -> 30
- 路由：EvidencePlanner 按题型决定 ES 直连或 PageIndex
- 生成：precision_v3 证据选择、事实核验、最终答案审计

Qwen3/Conan 相关配置、缓存和脚本作为实验记录保留，但不再作为当前主线。

## 顶层目录

| 路径 | 用途 | 清理原则 |
|---|---|---|
| `configs/` | 基线、消融、索引构建配置；也是实验复现记录 | 保留，不随意移动 |
| `src/` | RAG 核心实现 | 保留 |
| `tests/` | 核心行为、配置和回归测试 | 保留 |
| `docs/` | 当前交接、测试台账、基础设施说明和历史归档 | 当前文档放根层；旧报告放 `archive/` |
| `scripts/` | 配置生成、诊断、远程运维、启动脚本 | 按 `cfggen/diag/remote/start` 分类 |
| `outputs/` | 本地评测产物与构建日志 | 正式结果保留；构建日志归入 `outputs/archive/` |
| `.index_cache/` | 本地索引、chunks、manifest、tokenizer 缓存 | 成本高，不作为普通临时文件删除 |
| `corpus/` | 原始语料 | 不清理 |
| `deploy/` | ES 与服务器部署工具 | 保留 |

## RAG 核心代码

| 文件 | 责任 |
|---|---|
| `src/pipeline.py` | 总编排入口：加载配置、构建/加载索引、检索、重排、PageIndex 路由、生成、断点和评测 |
| `src/indexer.py` | 语料扫描、doc/chunk ID、三种切块分支、manifest/cache、BM25/FAISS 构建 |
| `src/embedder.py` | SentenceTransformers、OpenAI-compatible、Ollama、FastEmbed 等 embedding 适配 |
| `src/elasticsearch_backend.py` | ES mapping/index/bulk、BM25、dense、RRF hybrid、remote rerank |
| `src/retriever.py` | 本地 BM25/FAISS 检索与本地 rerank；ES 主线主要使用上一文件 |
| `src/pageindex_router.py` | EvidencePlanner 题型路由、原文解析为树、节点选择/审计、多跳补检索和 scoped fallback |
| `src/generator.py` | 证据限额和 precision_v3 选择、答案生成、事实核验、最终答案与引用审计 |
| `src/llm.py` | LLM provider 客户端、重试和请求配置 |
| `src/evaluator.py` | 答案校验、简单指标、官方评分器调用 |
| `src/build_es_index.py` | 独立 ES 全量索引构建入口 |
| `src/benchmark_embedding.py` | embedding 吞吐/形状基准工具 |
| `src/validate_submission.py` | 提交结果格式检查入口 |

## 切块实现并非仅两种

切块统一由 `src/indexer.py` 的 `Indexer._chunk_text()` 分发，目前有三条实现：

1. `method: fixed`
   - whitespace token 固定窗口；`chunk_size` 和 `chunk_overlap` 直接控制。
   - BGE 主线使用 `fixed-v2`，512/0。
   - Conan 的保守实验 `conan-v3-72-16` 也复用此实现，只是参数更小。

2. `method: hierarchical`
   - 自研标题/段落/句子感知切块，长度由本地 BGE tokenizer 近似计数。
   - 早期 Qwen3/Conan 索引使用 `hierarchical-v1-448`，448/32。
   - 因 Conan tokenizer 更密，部分块在 embedding 写入阶段仍会被 `__pN` 递归二分。

3. `method: langchain_conan_recursive`
   - 使用 `RecursiveCharacterTextSplitter`。
   - 长度函数使用 Conan 的本地 tokenizer，缺失时可调用 `/tokenize` 并缓存计数。
   - 配置 `langchain-conan-v1-448-32`，目标是生成时就满足 Conan 窗口，避免写 ES 时临时二分。

因此，“BGE 切块”和“Conan LangChain 切块”确实是两条重要路线，但代码层还保留了一条中间的自研 hierarchical 路线。

## 配置与结果保存规则

- 历史配置即实验参数记录，全部保留。
- 每次新测试使用新的 `pipeline.name` 和 PageIndex `cache_dir`。
- 评测现有索引应使用 `read_existing_index: true`。
- BGE 回退快照见 `docs/backups/BGE_RAG_ROLLBACK_SNAPSHOT_20260812.md`。
- 统一测试台账见 `docs/archive/ledgers/RAG_TEST_RECORD_THROUGH_20260812.md`。
