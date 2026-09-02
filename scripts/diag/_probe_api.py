"""Probe the Conan embedding API: per-request latency at different batch sizes.

Runs single API calls (32/128/512 texts) and reports elapsed time, so we can
pick the right batch/concurrency for the full build.
"""
import json
import os
import sys
import time
import urllib.request
from urllib.error import HTTPError, URLError

API = "http://10.72.55.209:7993/v1/embeddings"
KEY = os.environ.get("EMBEDDING_API_KEY", "123456")


def load_texts(n):
    """Load normal-length texts only (real 448-token chunks never exceed the
    API 512-token cap; the local demo cache contains oversized legacy rows)."""
    texts = []
    with open(".index_cache/chunks.jsonl", encoding="utf-8") as f:
        for line in f:
            text = json.loads(line).get("text", "")
            if len(text) > 1200:  # ~<350 tokens, skip demo outliers
                continue
            texts.append(text)
            if len(texts) >= n:
                break
    return texts


def call(texts):
    body = json.dumps({
        "model": "embedding", "input": texts, "encoding_format": "float",
    }).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {KEY}",
    })
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = data.get("data", [])
        elapsed = time.time() - start
        print(f"batch={len(texts)}: {elapsed:.1f}s -> {len(items)} vectors, "
              f"{len(texts) / elapsed:.1f} texts/s")
        return True
    except HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        print(f"batch={len(texts)}: HTTP {e.code} {detail[:200]}")
        return False
    except URLError as e:
        print(f"batch={len(texts)}: conn error {e}")
        return False


def main():
    texts = load_texts(600)
    for n in (32, 128, 512):
        call(texts[:n])
    return 0


if __name__ == "__main__":
    sys.exit(main())
