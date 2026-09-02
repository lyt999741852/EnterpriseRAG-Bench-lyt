# BGE 500 题 RAG + PageIndex 核心代码包

这是从当前 EnterpriseRAG-Bench 工作区提取的 BGE 500 题 question-only 测评核心包，供 mentor 或新的会话窗口快速理解和迁移当前架构。

本包包含在线 RAG 主链路、PageIndex 对接、500 题配置、架构图和最小代码测试；不包含语料库、Elasticsearch 索引、PageIndex 外部仓库、答案结果或任何 API Key。

## 包内内容

```text
portable_bge500_rag_pageindex_core/
├── src/                         # RAG、ES、embedding、生成、PageIndex、评测适配
├── configs/
│   ├── bge500_question_only_pageindex.yaml  # 可迁移运行配置
│   ├── snapshots/              # 原始 500 题冻结配置和 no-correction 快照
│   └── eval_pageindex_ab50...  # 当前 50 题架构验证配置，供对照理解
├── docs/
│   ├── BGE_RAG_ARCHITECTURE_REPORT_20260820.md
│   └── assets/                 # 可直接插入飞书的 PNG 架构图
├── reference/                  # 500 题结果参考快照
├── tests/                      # 核心单元测试
├── requirements.txt
└── README.md
```

## 运行前需要重新接入的外部资源

新电脑或新会话只需要重新准备以下资源，代码架构不需要改变：

1. `corpus/all_documents`：原始企业文档目录。
2. `questions.jsonl`：官方 500 题问题文件。在线 RAG 只读取每题的 `question`；benchmark 的题型、参考答案和 expected documents 不进入检索或生成链路。
3. 已构建的 Elasticsearch 索引：默认配置为 `enterprise-rag-bge-small-v1`，当前代码按只读模式连接。
4. `.index_cache/full_es_bge_small/manifest.sqlite3`：PageIndex 通过它把 `doc_id` 映射回原文路径。
5. PageIndex 外部仓库：放到 `vendor/PageIndex`，或把配置中的 `pageindex.home` 改成实际路径。
6. LLM API 和 reranker API：按新环境修改配置中的 `api_base`。

API 密钥只通过环境变量传递，不写入配置文件：

```powershell
$env:LARK_API_KEY = "<LLM API key>"
$env:EMBEDDING_API_KEY = "<reranker API key>"
```

不要把真实值提交到代码包、配置、命令记录或日志中。

## 运行 500 题生成

在包根目录执行：

```powershell
python -m pip install -r requirements.txt
python -m src.pipeline configs/bge500_question_only_pageindex.yaml
```

当前配置的关键行为：

```yaml
pipeline:
  question_only: true
  question_router:
    enabled: true
  read_existing_index: true

pageindex:
  enabled: true

evaluation:
  enabled: false
```

`evaluation.enabled=false` 表示生成进程不自动启动官方评分。生成完成并通过 `validation.json` 后，再用官方评测程序独立执行：

```text
metrics_based_eval --no-correction
```

这样可以确保评分只使用冻结后的 `answers.jsonl`，不把官方 gold 修正流程混入 RAG 运行过程。

## 端到端架构摘要

```text
question-only
  → LLM 根据问题文本推断内部路由模式
  → 按题型选择 keyword / dense / rewrite / answer-intent 视图
  → 带权 RRF
  → remote reranker：120 → 30
  → semantic consensus rescue：最多补 1 个文档
  → PageIndex：文档树、节点选择、缺失分面追检索、权威性审计
  → precision_v3：24 个候选 → 最多 10 个证据
  → 事实核验和最终答案/来源审计
  → answers.jsonl
```

题型路由使用的是模型根据问题文本生成的**内部标签**，不是输入中的官方题型标签。不同内部模式主要影响两件事：

- 检索视图：`semantic` / `project_related` 增加 rewrite 和 answer-intent；`completeness` 增加 answer-intent。
- PageIndex 证据预算：单文档、多文档、冲突配对、穷举和 corpus-level 模式分别使用不同候选文档数、节点数和 hop 数。

PageIndex 的核心跳转是“**三关两跳**”：

1. 候选文档关：`doc_id` 去重、manifest 回读原文、构建或读取文档树。
2. 节点证据关：定位直接支持答案的章节，排除错实体、错日期、错版本。
3. 完整性审计关：检查 facets 覆盖、权威性、冲突和重复对象。
4. 如果缺分面且仍有预算，第二跳只检索缺失分面，并保留第一跳已审计证据。
5. 完整时形成证据闭集；部分时只在已准入文档内扩展；完全失败才按题型决定 ES fallback 或拒答。

详细说明见 [`docs/BGE_RAG_ARCHITECTURE_REPORT_20260820.md`](docs/BGE_RAG_ARCHITECTURE_REPORT_20260820.md)。

## 500 题冻结结果参考

当前已完成的 BGE 500 题官方 `no-correction` 快照：

| Questions | Correctness | Completeness | Combined | Recall | Invalid Extra Docs |
|---:|---:|---:|---:|---:|---:|
| 500 | 60.60% | 62.57% | **55.18** | 61.12% | 0.18 |

参考文件：[`configs/snapshots/BGE500_NO_CORRECTION_SNAPSHOT_20260818.json`](configs/snapshots/BGE500_NO_CORRECTION_SNAPSHOT_20260818.json)。该结果是已完成的冻结基线，新机器接入资源后可用同一配置复现或继续优化。

## 代码阅读顺序

建议 mentor 或新会话按以下顺序阅读：

1. `src/pipeline.py`：总流程、question-only 隔离、多视图、RRF、PageIndex 调用和检查点。
2. `src/pageindex_router.py`：题型证据计划、文档树、节点选择、多跳和审计。
3. `src/elasticsearch_backend.py`：BM25、dense、hybrid、递归分片折叠和 reranker。
4. `src/generator.py`：precision_v3、事实核验、最终答案与引用审计。
5. `configs/bge500_question_only_pageindex.yaml`：500 题运行参数和外部资源接口。
6. `docs/BGE_RAG_ARCHITECTURE_REPORT_20260820.md`：汇报版架构说明及静态图。

## 迁移边界

本包是“代码和配置快照”，不是完整数据迁移包。为了控制体积和保护数据，以下内容需要由接收方自行准备或通过独立渠道挂载：

- 约 51 万份原始文档；
- BGE 向量模型缓存；
- Elasticsearch 服务和约 90 万级 chunk 索引；
- PageIndex 源码与运行环境；
- LLM、embedding/reranker 服务和密钥；
- 官方评测脚本。
