"""Decisive concurrency probe: same 1024 real chunks, 1/2/4/8 concurrent requests.

Each request carries 128 texts (~1000 chars each). If the server parallelizes,
wall time stays ~flat as workers increase; if it serializes, wall time grows
linearly with workers.
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
CHAR_CAP = 1000
GROUP = 128
TOTAL = 1024


def pre_split(text):
    if len(text) <= CHAR_CAP:
        return [text]
    pieces = []
    rest = text
    while len(rest) > CHAR_CAP:
        cut = rest.rfind(" ", 0, CHAR_CAP)
        if cut <= 0:
            cut = CHAR_CAP
        pieces.append(rest[:cut])
        rest = rest[cut:].lstrip()
    if rest:
        pieces.append(rest)
    return pieces


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
        results[idx] = (0, time.time() - start, f"HTTP {e.code} {detail[:300]}")
    except URLError as e:
        results[idx] = (0, time.time() - start, str(e))


def run(texts, workers):
    groups = [texts[i:i + GROUP] for i in range(0, len(texts), GROUP)]
    results = [None] * len(groups)
    lock = threading.Lock()
    next_idx = [0]

    def worker():
        while True:
            with lock:
                idx = next_idx[0]
                next_idx[0] += 1
            if idx >= len(groups):
                return
            call(groups[idx], results, idx)

    start = time.time()
    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.time() - start
    items = sum(r[0] for r in results if r)
    errors = [r[2] for r in results if r and r[2]]
    per = sorted(r[1] for r in results if r)
    print(f"workers={workers}: wall={wall:.1f}s items={items} rate={items / wall:.1f}/s "
          f"per_req_med={per[len(per) // 2]:.1f}s errors={len(errors)}", flush=True)
    if errors:
        for e in errors[:3]:
            print(f"    err: {e}", flush=True)


def main():
    raw = []
    with open(SAMPLE, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= 2048:
                break
            raw.append(json.loads(line).get("text", ""))
    texts = []
    for t in raw:
        texts.extend(pre_split(t))
        if len(texts) >= TOTAL:
            break
    texts = texts[:TOTAL]
    print(f"prepared {len(texts)} texts (avg {sum(len(t) for t in texts) / len(texts):.0f} chars)", flush=True)
    for workers in (1, 2, 4, 8):
        run(texts, workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
