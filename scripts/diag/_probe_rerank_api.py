"""Probe the private rerank endpoint with two non-sensitive documents."""
import json
import os
from urllib.request import Request, urlopen


count = int(os.environ.get("RERANK_PROBE_COUNT", "2"))
documents = [
    ("The plan includes ten million tokens per month. " * 80).strip()
    for _ in range(count)
]
payload = {
    "model": "rerank",
    "query": "token allowance",
    "documents": documents,
    "top_n": min(2, count),
    "return_documents": False,
}
request = Request(
    "http://10.72.55.209:7992/v1/rerank",
    data=json.dumps(payload).encode(),
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.environ.get('EMBEDDING_API_KEY', '')}",
    },
)
with urlopen(request, timeout=30) as response:
    print(response.status)
    print(response.read().decode())
