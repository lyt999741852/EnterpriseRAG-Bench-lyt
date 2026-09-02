# -*- coding: utf-8 -*-
"""One-shot integrity check for v3 conan448 chunks cache.

1) Count lines in chunks.jsonl
2) Count chunked docs in manifest.sqlite3
3) Sample ~500 chunks, count tokens with local conan_tokenizer (AutoTokenizer,
   add_special_tokens=True), report max / >512 counts.
"""
import json
import random
import sqlite3
import sys
import time
from pathlib import Path

CACHE = Path(r"D:\EnterpriseRAG-Bench\.index_cache\full_es_qwen3_emb_v3_conan448")
CHUNKS = CACHE / "chunks.jsonl"
MANIFEST = CACHE / "manifest.sqlite3"
TOKENIZER_DIR = r"D:\EnterpriseRAG-Bench\.index_cache\conan_tokenizer"
SAMPLE_N = 500
MAX_TOKENS = 512

t0 = time.time()


def count_lines_and_sample(path: Path, sample_n: int):
    """Single pass: count lines + reservoir sampling."""
    sample = []
    total = 0
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            total += 1
            if len(sample) < sample_n:
                sample.append(line)
            else:
                j = random.randint(0, total - 1)
                if j < sample_n:
                    sample[j] = line
    return total, sample


def manifest_chunked_docs(db_path: Path):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        # find the manifest table (usually 'manifest')
        table = "manifest" if "manifest" in tables else tables[0]
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
        print(f"[manifest] table={table} cols={cols}")
        # try common status columns
        for col in ("chunked", "status"):
            if col in cols:
                rows = con.execute(
                    f"SELECT {col}, COUNT(*) FROM {table} GROUP BY {col}").fetchall()
                print(f"[manifest] {col} distribution: {rows}")
                n_chunked = sum(c for s, c in rows if str(s).lower() in
                                ("chunked", "done", "1", "ok", "success"))
                n_total = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                return n_total, n_chunked
        n_total = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return n_total, None
    finally:
        con.close()


def main():
    random.seed(20260813)
    print(f"[check] chunks.jsonl: {CHUNKS} ({CHUNKS.stat().st_size / 1e9:.2f} GB)")
    total, sample = count_lines_and_sample(CHUNKS, SAMPLE_N)
    print(f"[check] chunks.jsonl lines = {total} (in {time.time() - t0:.0f}s)")

    n_total, n_chunked = manifest_chunked_docs(MANIFEST)
    print(f"[manifest] total docs = {n_total}, chunked docs = {n_chunked}")
    if n_chunked is not None:
        print(f"[check] lines vs chunked docs: {total} vs {n_chunked} "
              f"-> {'MATCH' if total == n_chunked else 'MISMATCH'}")
        # chunks.jsonl may contain multi-chunk docs; manifest counts docs, so
        # also print per-doc ratio expectation from _meta.json
        meta = json.loads((CACHE / "_meta.json").read_text(encoding="utf-8"))
        print(f"[meta] num_docs={meta.get('num_docs')} "
              f"num_chunks={meta.get('num_chunks')}")

    # tokenizer check
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(TOKENIZER_DIR)
    max_tok = 0
    over = 0
    over_samples = []
    lens = []
    for line in sample:
        try:
            obj = json.loads(line)
            text = obj.get("text") or obj.get("content") or obj.get("chunk_text") or ""
        except Exception:
            text = line.strip()
        n = len(tok.encode(text, add_special_tokens=True))
        lens.append(n)
        if n > max_tok:
            max_tok = n
        if n > MAX_TOKENS:
            over += 1
            if len(over_samples) < 5:
                over_samples.append((n, text[:120]))
    lens.sort(reverse=True)
    print(f"[token] sampled={len(sample)} max_tokens={max_tok} "
          f"> {MAX_TOKENS}: {over}")
    print(f"[token] top5 lens: {lens[:5]}")
    for n, t in over_samples:
        print(f"[token] OVER {n}: {t!r}")


if __name__ == "__main__":
    sys.exit(main())
