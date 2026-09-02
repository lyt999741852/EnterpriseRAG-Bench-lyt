"""Calibrate local whitespace-token chunk sizes against Conan's API limit."""

from __future__ import annotations

import json
import random
import re
import threading
import urllib.error
import urllib.request


URL = "http://10.72.55.209:7993/v1/embeddings"
KEY = "123456"
PATH = "/opt/enterprise-rag-bench/app/.index_cache/full_es_qwen3_emb/chunks.jsonl"
LIMIT = 512
SAMPLE_SIZE = 1000


def api_tokens(text: str) -> tuple[int | None, str]:
    body = json.dumps({
        "model": "embedding",
        "input": [text],
        "encoding_format": "float",
    }).encode("utf-8")
    req = urllib.request.Request(URL, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {KEY}",
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return int(payload.get("usage", {}).get("prompt_tokens", 0)), "ok"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        match = re.search(r"has (\d+) input tokens", detail)
        if exc.code == 400 and match:
            return int(match.group(1)), "over"
        return None, f"HTTP {exc.code}"


def main() -> None:
    rows = []
    with open(PATH, encoding="utf-8") as handle:
        for line in handle:
            rows.append(json.loads(line))
    random.Random(20260807).shuffle(rows)
    rows = rows[:SAMPLE_SIZE]
    out: list[tuple[int | None, str] | None] = [None] * len(rows)
    cursor = 0
    lock = threading.Lock()

    def worker() -> None:
        nonlocal cursor
        while True:
            with lock:
                if cursor >= len(rows):
                    return
                i = cursor
                cursor += 1
            out[i] = api_tokens(rows[i].get("text", ""))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    measured = []
    for row, result in zip(rows, out):
        api_count, status = result or (None, "missing")
        local_words = len(re.findall(r"\S+", row.get("text", "")))
        measured.append((local_words, len(row.get("text", "")), api_count, status))

    valid = [item for item in measured if item[2] is not None]
    over = [item for item in valid if item[3] == "over" or item[2] > LIMIT]
    print(f"sample={len(measured)} measured={len(valid)} over512={len(over)} "
          f"over_rate={len(over) / len(valid):.3f}")
    for p in (50, 90, 95, 99, 100):
        vals = sorted(item[2] for item in valid)
        print(f"api_tokens_p{p}={vals[min(len(vals) - 1, len(vals) * p // 100)]}")
    for threshold in (128, 160, 192, 224, 256, 288, 320, 352, 384, 400, 416, 448):
        selected = [item for item in valid if item[0] <= threshold]
        bad = [item for item in selected if item[2] > LIMIT]
        print(f"local_words<={threshold}: n={len(selected)} "
              f"over={len(bad)} rate={len(bad) / len(selected):.4f}" if selected else
              f"local_words<={threshold}: n=0")
    for threshold in (512, 640, 768, 896, 1024, 1152, 1280, 1408):
        selected = [item for item in measured if item[1] <= threshold and item[2] is not None]
        bad = [item for item in selected if item[2] > LIMIT]
        print(f"chars<={threshold}: n={len(selected)} "
              f"over={len(bad)} rate={len(bad) / len(selected):.4f}" if selected else
              f"chars<={threshold}: n=0")


if __name__ == "__main__":
    main()
