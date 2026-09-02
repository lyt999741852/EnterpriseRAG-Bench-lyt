"""Calibrate bge-tokenizer vs embedding-API token counts on a sample."""
import json
import random
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, "/opt/enterprise-rag-bench/app")

from src.indexer import _get_tokenizer

URL = "http://10.72.55.209:7993/v1/embeddings"
KEY = "123456"
API_LIMIT = 512

tok = _get_tokenizer()


def api_tokens(texts):
    """Return API token counts for texts (single-shot each for exact usage)."""
    counts = []
    for text in texts:
        body = json.dumps({"model": "embedding", "input": [text]}).encode()
        req = urllib.request.Request(URL, data=body, headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        counts.append(data.get("usage", {}).get("total_tokens", 0))
        time.sleep(0.01)
    return counts


def api_tokens_safe(texts, batch_size=64):
    """Single-shot per-item token counts with 400-error tolerance."""
    counts: list[int | None] = []
    for text in texts:
        body = json.dumps({"model": "embedding", "input": [text]}).encode()
        req = urllib.request.Request(URL, data=body, headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
            counts.append(data.get("usage", {}).get("total_tokens", 0))
        except urllib.error.HTTPError as e:
            if e.code != 400:
                raise
            counts.append(None)  # oversized
        time.sleep(0.01)
    return counts


def main() -> int:
    random.seed(42)
    sample: list[dict] = []
    with open("/opt/enterprise-rag-bench/app/.index_cache/full_es_qwen3_emb/chunks.jsonl", encoding="utf-8") as f:
        for line in f:
            sample.append(json.loads(line))
    sample = random.sample(sample, min(3000, len(sample)))

    texts = [r["text"] for r in sample]
    api_counts = api_tokens_safe(texts)
    bge_counts = [
        len(tok.encode(t, add_special_tokens=False, verbose=False)) for t in texts
    ]

    pairs = [(b, a) for b, a in zip(bge_counts, api_counts) if a is not None]
    ratios = [a / b for b, a in pairs if b > 0]
    ratios.sort()
    n = len(ratios)
    print(f"sampled {len(sample)}, measured {n}")
    for p in [50, 90, 95, 99, 100]:
        if n:
            print(f"  ratio p{p}: {ratios[min(n - 1, n * p // 100)]:.3f}")
    print(f"  ratio max: {ratios[-1]:.3f} (bge={pairs[ratios.index(ratios[-1])][0]})")

    overs = [(b, a) for b, a in pairs if a is not None and a > API_LIMIT]
    print(f"  API>512 samples: {len(overs)}")
    for b, a in overs[:10]:
        print(f"    bge={b} api={a} ratio={a / b:.2f}")
    if overs:
        b_min = min(b for b, _ in overs)
        print(f"  min bge count among API>512: {b_min}")
    # what bge threshold keeps api<=512 with margin?
    safe_b = max((b for b, a in pairs if a is not None and a <= int(API_LIMIT * 0.9)), default=0)
    print(f"  max bge count with api<=460: {safe_b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
