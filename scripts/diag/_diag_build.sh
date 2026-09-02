#!/bin/bash
echo "=== process state ==="
cat /proc/38643/status 2>/dev/null | grep -E 'State|Threads' || echo "proc gone"
echo "=== sockets ==="
ss -tnp 2>/dev/null | grep 38643 | head -5 || echo "no sockets"
echo "=== API connectivity ==="
python3 << 'EOF'
import json, time, urllib.request
body = json.dumps({'model': 'embedding', 'input': ['quick connectivity test sentence']}).encode()
req = urllib.request.Request(
    'http://10.72.55.209:7993/v1/embeddings', data=body,
    headers={'Content-Type': 'application/json', 'Authorization': 'Bearer 123456'})
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode())
    print('API OK %.2fs usage=%s' % (time.time() - t0, d.get('usage')))
except Exception as e:
    print('API FAIL after %.2fs: %s' % (time.time() - t0, e))
EOF
echo "=== ES index state ==="
curl -s -m 10 'http://127.0.0.1:9200/enterprise-rag-qwen3-emb-v1/_count' | head -c 150
echo
