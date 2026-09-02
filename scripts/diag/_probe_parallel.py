"""Decisive probe: does the embedding API serve requests in parallel?

Measures wall time of 128 real 448-token chunks sent as:
  - one request of 128
  - two concurrent requests of 64
  - four concurrent requests of 32

If the server is parallel, the concurrent runs take ~the same wall time as
the single run; if it serializes, they take ~2x / ~4x.
"""
import json
import os
import sys
import threading
import time
import urllib.request
from urllib.error import HTTPError, URLError

API = "http://10.72.55.209:7993/v1/embeddings"
KEY = os.environ.get("EMBEDDING_API_KEY", "123456")
SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_sample_v2_chunks.jsonl")


def load_texts(n):
    texts = []
    with open(SAMPLE, encoding="utf-8") as f:
        for line in f:
            texts.append(json.loads(line).get("text", ""))
            if len(texts) >= n:
                break
    return texts


def call(texts, results, idx):
    body = json.dumps({
        "model": "embedding", "input": texts, "encoding_format": "float",
    }).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {KEY}",
    })
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = data.get("data", [])
        results[idx] = (len(items), time.time() - start, None)
    except HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        results[idx] = (0, time.time() - start, f"HTTP {e.code} {detail[:150]}")
    except URLError as e:
        results[idx] = (0, time.time() - start, str(e))


def run_concurrent(texts, n_workers):
    chunk_size = len(texts) // n_workers
    results = [None] * n_workers
    start = time.time()
    threads = []
    for i in range(n_workers):
        part = texts[i * chunk_size:(i + 1) * chunk_size]
        t = threading.Thread(target=call, args=(part, results, i))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    wall = time.time() - start
    items = sum(r[0] for r in results)
    errors = [r[2] for r in results if r[2]]
    per = [r[1] for r in results]
    print(f"workers={n_workers} (each {chunk_size}): wall={wall:.1f}s "
          f"items={items} per_req={[round(p, 1) for p in per]} errors={errors}", flush=True)
    return wall


def main():
    texts = load_texts(128)
    print(f"loaded {len(texts)} real chunks", flush=True)
    run_concurrent(texts, 1)
    run_concurrent(texts, 2)
    run_concurrent(texts, 4)
    return 0


if __name__ == "__main__":
    sys.exit(main())
