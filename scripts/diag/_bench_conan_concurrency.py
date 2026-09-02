"""Measure Conan single-input embedding throughput versus concurrency."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request


URL = os.environ.get("EMBEDDING_URL", "http://10.72.55.209:7993/v1/embeddings")
KEY = os.environ.get("EMBEDDING_API_KEY", "123456")
MODEL = "embedding"


def one_call(text: str) -> tuple[bool, float, str]:
    body = json.dumps({
        "model": MODEL,
        "input": [text],
        "encoding_format": "float",
    }).encode("utf-8")
    req = urllib.request.Request(URL, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {KEY}",
    })
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
        vector = payload.get("data", [{}])[0].get("embedding", [])
        if len(vector) != 1792:
            return False, time.perf_counter() - started, f"dim={len(vector)}"
        return True, time.perf_counter() - started, ""
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:180]
        return False, time.perf_counter() - started, f"HTTP {exc.code} {detail}"
    except Exception as exc:  # pragma: no cover - diagnostic script
        return False, time.perf_counter() - started, repr(exc)


def run(concurrency: int, total: int = 128) -> None:
    # 400 simple words stay below the Conan 512-token per-input window while
    # keeping request/response cost close to a full production chunk.
    text = "word " * 400
    results: list[tuple[bool, float, str] | None] = [None] * total
    cursor = 0
    lock = threading.Lock()

    def worker() -> None:
        nonlocal cursor
        while True:
            with lock:
                if cursor >= total:
                    return
                index = cursor
                cursor += 1
            results[index] = one_call(text)

    started = time.perf_counter()
    threads = [threading.Thread(target=worker) for _ in range(concurrency)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    elapsed = time.perf_counter() - started
    ok = sum(bool(item and item[0]) for item in results)
    errors = [item[2] for item in results if item and not item[0]]
    latencies = [item[1] for item in results if item and item[0]]
    p95 = sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)] if latencies else 0
    print(json.dumps({
        "concurrency": concurrency,
        "total": total,
        "ok": ok,
        "errors": len(errors),
        "wall_seconds": round(elapsed, 2),
        "requests_per_second": round(ok / elapsed, 2) if elapsed else 0,
        "p95_latency_seconds": round(p95, 2),
        "first_error": errors[0] if errors else "",
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    for level in (1, 2, 4, 8, 16, 32, 64):
        run(level)
