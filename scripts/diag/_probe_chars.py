"""Empirical mapping: chars -> API tokens for the Conan embedding API.

Sends single texts of increasing length and reads the API-reported token
count from 400 errors (or success). Output is used to pick a safe char cap
so chunks never exceed the API 512-token limit.
"""
import json
import os
import re
import sys
import urllib.request
from urllib.error import HTTPError, URLError

API = "http://10.72.55.209:7993/v1/embeddings"
KEY = os.environ.get("EMBEDDING_API_KEY", "123456")
SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_sample_v2_chunks.jsonl")

TARGETS = [400, 700, 1000, 1300, 1600, 2000, 2500, 3000, 3500]


def load_by_len(target):
    best = None
    with open(SAMPLE, encoding="utf-8") as f:
        for line in f:
            text = json.loads(line).get("text", "")
            if len(text) < 300:
                continue
            if best is None or abs(len(text) - target) < abs(len(best) - target):
                best = text
    return best


def probe(text):
    body = json.dumps({
        "model": "embedding", "input": [text], "encoding_format": "float",
    }).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {KEY}",
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return len(data.get("data", [])), None
    except HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        m = re.search(r"has (\d+) input tokens", detail)
        return None, int(m.group(1)) if m else None
    except URLError as e:
        return None, str(e)


def main():
    print("chars -> api_tokens")
    for target in TARGETS:
        text = load_by_len(target)
        if text is None:
            continue
        n_vec, api_tokens = probe(text)
        status = f"OK({n_vec})" if n_vec else f"api={api_tokens}"
        print(f"{len(text):5d} chars -> {status}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
