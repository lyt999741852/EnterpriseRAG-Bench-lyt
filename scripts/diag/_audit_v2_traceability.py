"""Read-only traceability audit for the v2 ES index on the build server.

The script streams only ES document IDs and compares them with the current
server-side chunks.jsonl. It never writes to Elasticsearch or the cache.
"""

from __future__ import annotations

import os

import paramiko


REMOTE_SCRIPT = r'''
import json
import re
import sys
from urllib.request import Request, urlopen

ES = "http://10.72.100.29:31920"
INDEX = "enterprise-rag-qwen3-emb-v2"
CACHE = "/opt/enterprise-rag-bench/app/.index_cache/full_es_qwen3_emb/chunks.jsonl"

base_ids = set()
with open(CACHE, encoding="utf-8") as handle:
    for line in handle:
        item = json.loads(line)
        base_ids.add(item["chunk_id"])

def call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(ES + path, data=data, method=method,
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode())

first = call("POST", f"/{INDEX}/_search?scroll=5m", {
    "size": 2000, "_source": False, "sort": ["_doc"],
    "query": {"match_all": {}},
})
scroll_id = first["_scroll_id"]
hits = first["hits"]["hits"]
counts = {"exact_base": 0, "valid_split": 0, "unmapped": 0}
represented_base_ids = set()
examples = []
split_suffix = re.compile(r"(?:__p[0-9]+)+$")
scanned = 0
while hits:
    for hit in hits:
        doc_id = hit["_id"]
        scanned += 1
        if doc_id in base_ids:
            counts["exact_base"] += 1
            represented_base_ids.add(doc_id)
            continue
        base_id = split_suffix.sub("", doc_id)
        if base_id != doc_id and base_id in base_ids:
            counts["valid_split"] += 1
            represented_base_ids.add(base_id)
            continue
        counts["unmapped"] += 1
        if len(examples) < 20:
            examples.append(doc_id)
    page = call("POST", "/_search/scroll", {"scroll": "5m", "scroll_id": scroll_id})
    scroll_id = page.get("_scroll_id", scroll_id)
    hits = page["hits"]["hits"]

try:
    call("DELETE", "/_search/scroll", {"scroll_id": [scroll_id]})
except Exception:
    pass

mapping = call("GET", f"/{INDEX}/_mapping")
properties = mapping[INDEX]["mappings"]["properties"]
model_terms = call("POST", f"/{INDEX}/_search", {
    "size": 0,
    "aggs": {"models": {"terms": {"field": "embedding_model", "size": 20}}},
})
print(json.dumps({
    "cache_base_chunks": len(base_ids),
    "es_scanned": scanned,
    "id_classification": counts,
    "represented_cache_base_chunks": len(represented_base_ids),
    "missing_cache_base_chunks": len(base_ids - represented_base_ids),
    "unmapped_examples": examples,
    "embedding_dims": properties.get("embedding", {}).get("dims"),
    "embedding_model_field": properties.get("embedding_model", {}),
    "embedding_model_values": model_terms["aggregations"]["models"]["buckets"],
}, ensure_ascii=False, indent=2))
'''


def main() -> int:
    password = os.environ.get("SSH_PASS", "") or "XAznv@(2018)"
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("10.72.100.29", username="root", password=password, timeout=15)
    try:
        stdin, stdout, stderr = client.exec_command("python3 -", timeout=900)
        stdin.write(REMOTE_SCRIPT)
        stdin.channel.shutdown_write()
        print(stdout.read().decode("utf-8", "replace"))
        errors = stderr.read().decode("utf-8", "replace")
        if errors:
            print(errors)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
