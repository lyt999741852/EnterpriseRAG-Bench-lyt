# EnterpriseRAG-Bench 本地 RAG 基线

当前仓库包含可运行的 BM25、Dense 和 Hybrid RAG 流水线。默认 GitHub 子集使用严格来源筛选，共 39 道 GitHub-only 问题；完整配置处理全部 500 道问题。

## 已实现的可靠性能力

- SQLite 文档 manifest，记录文件状态、大小、时间、内容哈希和失败原因；
- 单文件读取失败自动隔离，不再终止整个索引任务；
- 确定性 chunk ID、预处理 checkpoint 和中断恢复；
- 语料、切块、Embedding 和索引配置指纹，防止错误复用缓存；
- 分批生成向量并增量加入 FAISS，避免完整向量矩阵常驻内存；
- BM25 / Dense / RRF Hybrid，可选 Cross-Encoder reranker 和相邻 chunk 扩展；
- 答案原子保存、成功题复用、失败题重试和提交格式校验；
- 生成答案只提交真正进入 LLM 上下文的父文档 ID；
- 官方评测使用 `--results-file`、`--parallelism` 和 `--no-correction` 参数。

## 常用命令

运行自动化测试：

```powershell
python -m unittest discover -s tests -v
```

运行严格的 39 题 BM25 基线：

```powershell
$env:DEEPSEEK_API_KEY="从安全环境读取"
python -m src.pipeline configs/default.yaml
```

继续内部 Qwen 实验：

```powershell
$env:LARK_API_KEY="由内部网关要求的值"
python -m src.pipeline configs/qwen_internal.yaml
```

同一配置的后续运行会保留已有成功答案，仅重试空答案和 `[LLM_ERROR: ...]`。修复后的 Qwen 实验写入新的 `baseline_qwen_fixed` 目录，避免复用旧实验中证据不一致的结果；配置默认关闭 thinking，并把输出上限提高到 4096 tokens。

校验答案文件：

```powershell
python -m src.validate_submission `
  --questions questions.jsonl `
  --answers outputs/baseline_bm25/answers.jsonl `
  --source github `
  --source-mode exact
```

在 GPU 服务器上对 10,000 个 chunk 做 Embedding 压测：

```powershell
python -m src.benchmark_embedding `
  --config configs/full_gpu.yaml `
  --chunks 10000 `
  --output outputs/embedding_benchmark.json
```

## 缓存布局

```text
.index_cache/
├── demo_bm25/
├── demo_dense/
└── full_bge_small/
```

每个缓存包含 `_meta.json`、`manifest.sqlite3`、`chunks.jsonl`，以及按检索方式生成的 `bm25.pkl` 和/或 `faiss.index`。配置或语料变化后，指纹会阻止旧索引被误用。

## 尚需外部环境

- 完整语料的 GPU Embedding 压测和全量索引；
- Docker/Elasticsearch 或 OpenSearch 服务；
- 官方 `metrics_based_eval.py` 代码及 Judge API；
- 最终 500 题生成、正式评分和排行榜提交。

`questions.jsonl` 中除 `question` 外的 gold 字段只用于离线统计与评估，不能传入检索器或生成器。
