"""Reproduce API hang: batch sizes 128/64/32 with real chunk texts."""
import json
import sys
import time
import urllib.request

URL = "http://10.72.55.209:7993/v1/embeddings"
KEY = "123456"


def call(texts, timeout=60):
    body = json.dumps({"model": "embedding", "input": texts}).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    return time.time() - t0, len(data.get("data", []))


def main() -> int:
    chunks = []
    with open("/opt/enterprise-rag-bench/app/.index_cache/full_es_qwen3_emb/chunks.jsonl", encoding="utf-8") as f:
        for line in f:
            chunks.append(json.loads(line)["text"])
            if len(chunks) >= 256:
                break
    lens = [len(t) for t in chunks]
    print(f"sample 256 chunks, text lens: min={min(lens)} max={max(lens)} avg={sum(lens)//len(lens)}", flush=True)
    for bs in [128, 64, 32, 16]:
        batch = chunks[:bs]
        try:
            dt, n = call(batch)
            print(f"batch {bs}: OK {dt:.2f}s items={n}", flush=True)
        except Exception as e:
            print(f"batch {bs}: FAIL {type(e).__name__}: {str(e)[:120]}", flush=True)
        time.sleep(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
