# Current RAG Architecture — 2026-08-18

当前主链路是 BGE-small + Elasticsearch hybrid retrieval + remote reranker + PageIndex evidence routing。
实验和评测均使用 question-only 输入，不把 benchmark 的题型、gold answer 或 expected document IDs 传入检索和生成链路。

```mermaid
flowchart TB
    Q["用户问题 / benchmark question-only"] --> ROUTER["LLM question router\n从问题文本推断题型"]

    ROUTER --> TYPE["inferred_question_type\nbasic / semantic / project / constrained / conflict / completeness ..."]
    Q --> VIEWS
    TYPE --> VIEWS

    subgraph VIEWS["多视图检索层"]
        K["Original keyword\n原始问题"] --> BM25["Elasticsearch BM25\n标题 + 正文关键词"]
        D["Original dense\n原始问题 embedding"] --> BGE["BGE-small-en-v1.5\n384 dim"]
        R["Query rewrite\nsemantic / project / completeness"] --> RD["Dense rewrite retrieval"]
        I["Answer intent query\nsemantic / project / completeness"] --> ID["Dense intent retrieval"]
        BM25 --> RRF
        BGE --> RRF
        RD --> RRF
        ID --> RRF
        RRF["Weighted RRF merge\n当前主链路权重：keyword 1.2\ndense 1.0 / rewrite 0.9 / intent 0.4"]
    end

    ES["ES read-only index\nenterprise-rag-bge-small-v1\n约 928,534 chunks"] --> BM25
    ES --> BGE
    ES --> RD
    ES --> ID

    RRF --> CAND["候选集合\n每路 ES candidate_k 240\nrerank 输入 candidate_k 120"]
    CAND --> RR["Remote reranker\n10.72.55.209:7992 /v1/rerank\ntop_n = 30"]

    RR --> PI_GATE["题型适配 / PageIndex gate"]

    subgraph PI["PageIndex evidence routing"]
        PI_GATE --> SIMPLE["Basic / miscellaneous / info-not-found\n简单或拒答路径"]
        PI_GATE --> TREE["Semantic / reasoning / constrained\nconflicting / project / completeness / high-level"]
        TREE --> DOCS["候选文档审计\nmax_candidate_documents = 24"]
        DOCS --> NODES["PageIndex 文档树 / 节点搜索\nmax_nodes_per_document = 40\nmax_followup_queries = 4\nmax_hops = 2"]
        NODES --> AUDIT["节点证据审计\nrequire_node_audit = true"]
        AUDIT --> PI_RESULT["PageIndex selected evidence"]
        TREE --> ES_FALLBACK["PageIndex 不完整时\nfallback_to_es_on_incomplete = true"]
        ES_FALLBACK --> PI_RESULT
        SIMPLE --> PI_RESULT
    end

    PI_RESULT --> EVIDENCE

    subgraph EVIDENCE["Evidence selection / answer preparation"]
        E1["precision_v3 evidence selector\ncandidate chunks = 24\nmax selected = 10\nmax chunks per doc = 4"]
        E2["fail-closed = true\n无充分证据时拒答/保守回答"]
        E3["Fact verification"]
        E4["Final answer audit"]
        E1 --> E2 --> E3 --> E4
    end

    EVIDENCE --> GEN["LLM answer generation\nLark / Qwen-compatible API\n10.72.100.35:7777/v1\ntemperature = 0\nmax_tokens = 8192"]
    GEN --> OUT["answers.jsonl\nanswer + document_ids\n最多 10 个文档 ID"]

    subgraph INFRA["索引、结构化与缓存"]
        CORPUS["corpus/all_documents\n约 511,961 source docs"]
        MANIFEST["manifest.sqlite3\n文档路径 / doc_id 映射"]
        PICACHE["PageIndex cache\n按 doc fingerprint 缓存树"]
        CORPUS --> MANIFEST
        MANIFEST --> PICACHE
        CORPUS --> ESBUILD["索引构建阶段\n当前评测 read_existing_index = true"]
        ESBUILD --> ES
        PICACHE --> NODES
    end

    subgraph EVAL["评测与实验控制"]
        OUT --> VALID["answers / IDs validation"]
        OUT --> TRACE["route_trace.jsonl\n题型来源、各视图、rerank、PageIndex"]
        OUT --> OFFICIAL["官方 metrics_based_eval\n固定 gold + --no-correction\n50 题优化 / 500 题诊断"]
        OFFICIAL --> METRICS["Correctness\nCompleteness\nOverall = mean(correct × completeness)\nRecall\nInvalid Extra Docs"]
        SUP["三组 50 题 supervisor\n候选池 -> 证据预算 -> 路由中性兜底\n串行执行，独立输出目录"] --> OUT
    end

    SNAP["500 题冻结快照\n配置 + answers + results + SHA256"] -.保护.-> OUT
```

## Current fixed configuration

- 主配置：[eval_pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817.yaml](../configs/eval_pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817.yaml)
- 500 题快照：[eval_pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817.yaml](../configs/snapshots/eval_pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817.yaml)
- 50 题实验使用同一固定题目集合、独立 `pipeline.name`、独立 PageIndex cache 和独立输出目录。
- 当前三组优化测试串行运行，避免同时占用 LLM、embedding、reranker 和 PageIndex 资源。

## Main bottleneck locations

目前从 Lexical A/B 结果看，BM25 权重变化没有改变最终 `document_ids`；候选池扩展还使 Overall 从 59.14 降到 59.01。因此后续瓶颈重点是：

1. LLM 路由是否把问题送入了不合适的 PageIndex / evidence 流程；
2. precision_v3 是否过度收缩了已经召回的证据；
3. 事实验证和 final answer audit 是否在低证据覆盖时过早拒答。
