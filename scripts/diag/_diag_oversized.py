"""Diagnose remaining oversized chunks (batch tokenize, background)."""
import json
import sqlite3
import sys

sys.path.insert(0, "/opt/enterprise-rag-bench/app")

from src.indexer import _get_tokenizer, _chunk_text_hierarchical

tok = _get_tokenizer()
samples = []
with open("/opt/enterprise-rag-bench/app/.index_cache/full_es_qwen3_emb/chunks.jsonl", encoding="utf-8") as f:
    batch = []
    for line in f:
        batch.append(json.loads(line))
        if len(batch) >= 4096:
            enc = tok([r["text"] for r in batch], add_special_tokens=False, verbose=False)
            for r, ids in zip(batch, enc["input_ids"]):
                if len(ids) > 448:
                    samples.append((r, len(ids)))
                    if len(samples) >= 8:
                        break
            if len(samples) >= 8:
                break
            batch = []

for r, n in samples:
    print(f"== {r['doc_id']} chunk={r['chunk_id'][-24:]} tokens={n}")
    print(f"   head: {r['text'][:140]!r}")
    print(f"   len: {len(r['text'])}", flush=True)

if samples:
    conn = sqlite3.connect("/opt/enterprise-rag-bench/app/.index_cache/full_es_qwen3_emb/manifest.sqlite3")
    rows = conn.execute("SELECT file_path, doc_id FROM documents").fetchall()
    conn.close()
    path_by_doc = {d: p for p, d in rows}
    for r, n in samples[:3]:
        rel = path_by_doc.get(r["doc_id"])
        if not rel:
            continue
        text = open(f"/opt/enterprise-rag-bench/app/corpus/all_documents/{rel}", encoding="utf-8", errors="replace").read()
        chunks = _chunk_text_hierarchical(text, 384, 64)
        mx = max((len(tok.encode(c["text"], add_special_tokens=False, verbose=False)) for c in chunks), default=0)
        print(f"re-chunk {r['doc_id']}: {len(chunks)} chunks, max={mx}", flush=True)
