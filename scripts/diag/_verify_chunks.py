"""Verify no oversized chunks remain in patched chunks.jsonl."""
import json
import sys

sys.path.insert(0, "/opt/enterprise-rag-bench/app")

from src.indexer import _get_tokenizer

tok = _get_tokenizer()
bad = 0
n = 0
batch = []
with open("/opt/enterprise-rag-bench/app/.index_cache/full_es_qwen3_emb/chunks.jsonl", encoding="utf-8") as f:
    for line in f:
        batch.append(json.loads(line))
        if len(batch) >= 4096:
            enc = tok([r["text"] for r in batch], add_special_tokens=False, verbose=False)
            bad += sum(1 for ids in enc["input_ids"] if len(ids) > 448)
            n += len(batch)
            batch = []
    if batch:
        enc = tok([r["text"] for r in batch], add_special_tokens=False, verbose=False)
        bad += sum(1 for ids in enc["input_ids"] if len(ids) > 448)
        n += len(batch)
print(f"checked {n} chunks, oversized: {bad}")
