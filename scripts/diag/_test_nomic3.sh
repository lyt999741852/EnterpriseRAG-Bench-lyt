#!/bin/bash
echo "=== /data06 embedding models format ==="
ls /data06/jina-embeddings-v3/ 2>/dev/null | head -8
ls /data06/embedding-models/ 2>/dev/null | head -10
ls /data06/Conan-embedding-v1/ 2>/dev/null | head -8
echo "=== nomic concurrent throughput (4/8/16 workers) ==="
python3 << 'EOF'
import json, time, urllib.request, concurrent.futures

def call_one(text):
    body = json.dumps({"model": "nomic-embed-text", "prompt": "search_document: " + text}).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/embeddings", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())["embedding"]

texts = ["batch item number %d with realistic enterprise text length words here" % i for i in range(64)]

for workers in [4, 8, 16]:
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(call_one, texts))
    dt = time.time() - t0
    print("workers %d: %.2fs (%.1f items/s)" % (workers, dt, 64 / dt), flush=True)
EOF
