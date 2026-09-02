#!/bin/bash
echo "=== ES bulk write benchmark (1024-dim vectors) ==="
python3 << 'EOF'
import json, time, urllib.request

URL = "http://127.0.0.1:9200"
INDEX = "enterprise-rag-e5-large-v1"

def es_request(method, path, payload=None):
    data = payload.encode() if isinstance(payload, str) else (json.dumps(payload).encode() if payload else None)
    req = urllib.request.Request(URL + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())

info = es_request("GET", f"/{INDEX}/_settings")
print("shards:", info[INDEX]["settings"]["index"].get("number_of_shards"))

vec = [0.01] * 1024
ops = []
for i in range(256):
    ops.append(json.dumps({"index": {"_index": INDEX, "_id": f"bench_{i}"}}, separators=(",", ":")))
    ops.append(json.dumps({"chunk_id": f"bench_{i}", "doc_id": f"benchdoc_{i}", "source_type": "bench",
                           "text": "benchmark", "chunk_index": i, "char_start": 0, "char_end": 4,
                           "embedding_model": "e5", "embedding": vec}, separators=(",", ":")))
t0 = time.time()
r = es_request("POST", "/_bulk", "\n".join(ops) + "\n")
dt = time.time() - t0
errs = sum(1 for it in r.get("items", []) if int(it.get("index", {}).get("status", 500)) >= 300)
print(f"bulk 256 docs (1024d): {dt:.2f}s -> {256/dt:.1f} docs/s, errors={errs}")

ops = []
for i in range(64):
    ops.append(json.dumps({"index": {"_index": INDEX, "_id": f"bench64_{i}"}}, separators=(",", ":")))
    ops.append(json.dumps({"chunk_id": f"bench64_{i}", "doc_id": f"benchdoc64_{i}", "source_type": "bench",
                           "text": "benchmark", "chunk_index": i, "char_start": 0, "char_end": 4,
                           "embedding_model": "e5", "embedding": vec}, separators=(",", ":")))
t0 = time.time()
r = es_request("POST", "/_bulk", "\n".join(ops) + "\n")
dt = time.time() - t0
print(f"bulk 64 docs (1024d): {dt:.2f}s -> {64/dt:.1f} docs/s")
EOF
