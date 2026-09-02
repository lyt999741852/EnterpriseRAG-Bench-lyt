#!/bin/bash
echo "=== ollama service ==="
ps aux | grep -E 'ollama (serve|runner)' | grep -v grep | head -3 || echo "ollama not running"
echo "=== ollama models ==="
ollama list 2>&1 | head -10
echo "=== nomic embed test (dim + latency) ==="
python3 << 'EOF'
import json, time, urllib.request

def call(texts, prefix=None):
    inputs = [f"{prefix}{t}" if prefix else t for t in texts]
    body = json.dumps({"model": "nomic-embed-text", "input": inputs}).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/embed", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode())
    return time.time() - t0, d

# warmup + dim
dt, d = call(["hello world"])
print("warmup %.2fs" % dt)
vecs = d.get("embeddings", [])
print("dim:", len(vecs[0]) if vecs else "N/A")

# batch speed: 128
texts = ["batch item number %d with realistic enterprise text length words" % i for i in range(128)]
dt, d = call(texts, prefix="search_document: ")
print("batch 128: %.2fs (%.1f items/s)" % (dt, 128 / dt))
print("dim batch:", len(d.get("embeddings", [[]])[0]))

# long text: 2000 tokens ~ 9000 chars
long_text = "long text test " * 2300
dt, d = call([long_text], prefix="search_document: ")
print("long 9k-char: %.2fs ok=%s" % (dt, bool(d.get("embeddings"))))

# prefix effect
dt, dq = call(["what is the company policy on remote work"], prefix="search_query: ")
dt, dd = call(["company policy states remote work is allowed"], prefix="search_document: ")
import math
def cos(a, b):
    return sum(x*y for x, y in zip(a, b)) / (math.sqrt(sum(x*x for x in a)) * math.sqrt(sum(x*x for x in b)))
print("cos(query,doc) with prefixes: %.4f" % cos(dq["embeddings"][0], dd["embeddings"][0]))
EOF
