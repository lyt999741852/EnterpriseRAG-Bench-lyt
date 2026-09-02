"""Compare Conan /tokenize counts with embedding usage on real cache chunks.

Read-only: samples cached v2 texts, makes no cache or Elasticsearch writes.
"""

from __future__ import annotations

import json
import os
import random
import sys
import urllib.request

ROOT = "/opt/enterprise-rag-bench/app"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def call(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + os.environ["EMBEDDING_API_KEY"],
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    with open(
        f"{ROOT}/.index_cache/full_es_qwen3_emb/chunks.jsonl", encoding="utf-8"
    ) as handle:
        rows = [json.loads(line) for line in handle]
    random.Random(20260812).shuffle(rows)
    samples = []
    skipped_over_448 = 0
    for row in rows:
        tokenized = call(
            "http://10.72.55.209:7993/tokenize",
            {"model": "embedding", "prompt": row["text"]},
        )
        if int(tokenized["count"]) > 448:
            skipped_over_448 += 1
            continue
        samples.append((row, int(tokenized["count"])))
        if len(samples) == 100:
            break
    differences = []
    for row, tokenize_count in samples:
        text = row["text"]
        embedded = call(
            "http://10.72.55.209:7993/v1/embeddings",
            {"model": "embedding", "input": [text], "encoding_format": "float"},
        )
        differences.append({
            "tokenize": tokenize_count,
            "embedding_usage": int(embedded["usage"]["prompt_tokens"]),
        })
    deltas = [item["embedding_usage"] - item["tokenize"] for item in differences]
    print(json.dumps({
        "sample_size": len(differences),
        "skipped_old_chunks_over_448": skipped_over_448,
        "all_equal": all(delta == 0 for delta in deltas),
        "delta_min": min(deltas),
        "delta_max": max(deltas),
        "examples": differences[:10],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
