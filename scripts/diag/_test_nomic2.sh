#!/bin/bash
echo "=== ollama version ==="
ollama --version 2>&1 | head -2
echo "=== nomic via /api/embeddings ==="
python3 << 'EOF'
import json, time, urllib.request, urllib.error

def call_single(text, prefix=None):
    body = json.dumps({"model": "nomic-embed-text", "prompt": f"{prefix}{text}" if prefix else text}).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/embeddings", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode())
    return time.time() - t0, d

# warmup + dim
dt, d = call_single("hello world")
print("warmup %.2fs" % dt)
print("dim:", len(d.get("embedding", [])))

# speed: 20 sequential single calls
texts = ["batch item number %d with realistic enterprise text length words" % i for i in range(20)]
t0 = time.time()
for t in texts:
    call_single(t, prefix="search_document: ")
dt = time.time() - t0
print("20 single calls: %.2fs (%.1f items/s)" % (dt, 20 / dt))

# long text 9k chars
long_text = "long text test " * 2300
try:
    dt, d = call_single(long_text, prefix="search_document: ")
    print("long 9k-char: %.2fs ok=%s" % (dt, bool(d.get("embedding"))))
except urllib.error.HTTPError as e:
    print("long 9k-char FAIL", e.code)

# prefix cosine sanity
dt, dq = call_single("what is the company policy on remote work", prefix="search_query: ")
dt, dd = call_single("company policy states remote work is allowed", prefix="search_document: ")
import math
def cos(a, b):
    return sum(x*y for x, y in zip(a, b)) / (math.sqrt(sum(x*x for x in a)) * math.sqrt(sum(x*x for x in b)))
print("cos(query,doc) prefixes: %.4f" % cos(dq["embedding"], dd["embedding"]))
EOF
