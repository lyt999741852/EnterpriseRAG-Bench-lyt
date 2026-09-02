"""Integrity check for the v3 Conan448 chunk cache and ES index.

Checks (per the project integrity checklist):
  1. chunks.jsonl line count vs manifest chunked docs & ES index count
  2. manifest status distribution + preprocess_complete metadata
  3. doc_id uniqueness in chunks.jsonl vs manifest chunked count
  4. random sample of 500 chunks: local Conan tokenizer, max tokens <= 448
     (hard cap 512)
"""
from __future__ import annotations

import json
import os
import random
import sqlite3
import sys
import time

CACHE = ".index_cache/full_es_qwen3_emb_v3_conan448"
CHUNKS = os.path.join(CACHE, "chunks.jsonl")
MANIFEST = os.path.join(CACHE, "manifest.sqlite3")
TOKENIZER_DIR = ".index_cache/conan_tokenizer"
ES_URL = "http://10.72.100.29:31920"
ES_INDEX = "enterprise-rag-qwen3-emb-v3-conan448"
SAMPLE_N = 500
EXPECTED_CHUNKS = 3_030_317


def count_lines_and_sample() -> tuple[int, int, list[dict]]:
    """Stream the file once: line count, unique doc_ids, reservoir sample."""
    t0 = time.time()
    lines = 0
    doc_ids: set[str] = set()
    reservoir: list[dict] = []
    with open(CHUNKS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            lines += 1
            if lines % 500_000 == 0:
                print(f"  scanned {lines:,} lines ({time.time()-t0:.0f}s)", flush=True)
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"  !! JSON error at line {lines}: {exc}")
                continue
            doc_ids.add(item.get("doc_id", ""))
            if len(reservoir) < SAMPLE_N:
                reservoir.append(item)
            else:
                j = random.randrange(lines)
                if j < SAMPLE_N:
                    reservoir[j] = item
    return lines, len(doc_ids), reservoir


def check_manifest() -> dict:
    conn = sqlite3.connect(MANIFEST)
    status = dict(conn.execute(
        "SELECT status, COUNT(*) FROM documents GROUP BY status"
    ).fetchall())
    meta = dict(conn.execute("SELECT key, value FROM metadata").fetchall())
    conn.close()
    return {"status": status, "meta": meta}


def check_token_lengths(sample: list[dict]) -> dict:
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(TOKENIZER_DIR, local_files_only=True)
    lens = [len(tok.encode(item["text"], add_special_tokens=True)) for item in sample]
    lens.sort()
    n = len(lens)
    return {
        "n": n,
        "max": lens[-1],
        "p99": lens[int(n * 0.99) - 1],
        "p95": lens[int(n * 0.95) - 1],
        "over_448": sum(1 for x in lens if x > 448),
        "over_512": sum(1 for x in lens if x > 512),
    }


def check_es_count() -> int:
    import urllib.request

    req = urllib.request.Request(f"{ES_URL}/{ES_INDEX}/_count")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return int(json.loads(resp.read())["count"])


def main() -> int:
    print(f"=== v3 Conan448 integrity check ({time.strftime('%F %T')}) ===")
    if not os.path.exists(CHUNKS):
        print(f"FAIL: {CHUNKS} not found")
        return 1

    print("[1/4] counting chunks.jsonl lines + sampling ...")
    lines, doc_ids, reservoir = count_lines_and_sample()
    print(f"  lines={lines:,}  unique_doc_ids={doc_ids:,}")
    print(f"  expected chunks: {EXPECTED_CHUNKS:,} -> "
          f"{'OK' if lines == EXPECTED_CHUNKS else 'MISMATCH!'}")

    print("[2/4] manifest check ...")
    man = check_manifest()
    print(f"  status: {man['status']}")
    print(f"  metadata preprocess_complete: {man['meta'].get('preprocess_complete')}")
    chunked_docs = man["status"].get("chunked", 0)
    print(f"  chunked docs vs unique doc_ids: {chunked_docs:,} vs {doc_ids:,} -> "
          f"{'OK' if chunked_docs == doc_ids else 'MISMATCH!'}")

    print(f"[3/4] token length check on {len(reservoir)} samples ...")
    tok = check_token_lengths(reservoir)
    print(f"  max={tok['max']} p99={tok['p99']} p95={tok['p95']} "
          f"over448={tok['over_448']} over512={tok['over_512']}")
    print(f"  -> {'OK' if tok['max'] <= 448 else 'OVER LIMIT!'}")

    print("[4/4] ES index count ...")
    es_count = check_es_count()
    print(f"  ES count: {es_count:,} vs chunks lines {lines:,} -> "
          f"{'OK' if es_count == lines else 'MISMATCH!'}")

    all_ok = (
        lines == EXPECTED_CHUNKS
        and chunked_docs == doc_ids
        and tok["max"] <= 448
        and es_count == lines
    )
    print(f"\nRESULT: {'ALL CHECKS PASSED' if all_ok else 'CHECKS FAILED'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
