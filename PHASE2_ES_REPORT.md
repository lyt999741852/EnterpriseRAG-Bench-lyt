# Elasticsearch Phase 1-2 Report

Completed on 2026-07-29 against the isolated Elasticsearch service on
`10.72.100.29`.

## Frozen model contract

- Embedding model: `BAAI/bge-small-en-v1.5`
- Hugging Face revision: `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`
- Runtime: SentenceTransformers 3.3.1 / PyTorch 2.5.1 / CUDA
- Vector dimension and similarity: 384 / cosine
- Generator: internal Qwen3.5-27B (`lark`)
- Index alias: `enterprise-rag-bge-small`

## Canary input

- Real GitHub documents: 8,052
- Deterministic fixed-v2 chunks produced: 14,335
- Chunks admitted to the phase-two index: 10,000
- File preprocessing failures: 0

## Measured result

- New vectors indexed: 10,000
- Failed bulk documents: 0
- Embedding plus bulk duration: 40.217 seconds
- End-to-end new indexing throughput: 248.65 chunks/second
- Elasticsearch document count: 10,000
- Elasticsearch primary store: approximately 108.1 MiB
- Cluster health: green
- Vector index type selected by Elasticsearch 8.19.12: `int8_hnsw`

The second identical run examined all 10,000 IDs, skipped all 10,000 as
existing, wrote zero new documents, and completed the ES resume check in
0.598 seconds. BM25, dense KNN, and weighted RRF hybrid retrieval smoke tests
all returned results for the multipart-upload benchmark query.

## Server artifacts

The runnable project and reports are under:

```text
/opt/enterprise-rag-bench/app
/opt/enterprise-rag-bench/app/.index_cache/canary_es_bge_small/
/opt/enterprise-rag-bench/model_cache
/opt/enterprise-rag-es/data
```

The next stage is to place `corpus/all_documents` on the server, run
`configs/full_es_qwen.yaml` without a chunk limit, verify the complete index,
then execute the 10, 50, and 500-question evaluation gates.
