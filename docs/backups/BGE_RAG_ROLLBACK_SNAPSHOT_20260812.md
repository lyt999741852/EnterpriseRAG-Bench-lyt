# BGE RAG rollback snapshot

Created before Qwen3-specific retrieval adaptation on 2026-08-12.

## Protected baseline

- Configuration: `configs/eval_pageindex_balanced50_bge_rerank_cpu.yaml`
- ES index / alias: `enterprise-rag-bge-small-v1` / `enterprise-rag-bge-small`
- Cache and manifest: `.index_cache/full_es_bge_small`
- PageIndex cache: `.pageindex_cache/balanced50_bge_rerank_cpu_20260810`
- Historical output name: `pageindex_balanced50_bge_rerank_cpu_20260810`
- Verified 50-question result: correctness 62.00, completeness 66.49,
  combined 58.74, document recall 66.19, invalid extra documents 0.17.

## Integrity record

At snapshot time, the following SHA-256 values were recorded:

| File | SHA-256 |
|---|---|
| `configs/eval_pageindex_balanced50_bge_rerank_cpu.yaml` | `190A35C81166460C0428201000987A1E8375C697B078FDDC7E97AB6572DA1650` |
| `src/elasticsearch_backend.py` | `467012A6A8A62249B0B2944733EFFCC846B99FFA4AE885535F7E886C8207D753` |
| `src/pipeline.py` | `40BBB9BAACD448FC1D5A42F78162117B0E852F65072A3BF85D5A59269F30ADCA` |

Qwen3 adaptation experiments must use new `pipeline.name` and PageIndex cache
paths. They must set `read_existing_index: true` and must never write to,
delete, or repoint the BGE index, alias, cache, or historical outputs.

## Rollback procedure

1. Use the protected BGE configuration above unchanged.
2. Verify the BGE alias and its cache manifest before running it.
3. Use a new output name for any revalidation; do not overwrite the protected
   historical output.
4. Compare the new result to the protected 58.74 combined score.

