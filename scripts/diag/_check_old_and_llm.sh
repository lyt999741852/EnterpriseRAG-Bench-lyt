#!/bin/bash
echo "=== old library build report (bge-small) ==="
cat /opt/enterprise-rag-bench/app/.index_cache/full_es_bge_small/es_build_report.json 2>/dev/null | head -30
echo "=== old build logs ==="
ls -la /opt/enterprise-rag-bench/app/outputs/*.log 2>/dev/null | grep -i -E 'build|index|phase' | head -5
echo "=== qwen LLM API concurrent throughput ==="
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
python3 << 'EOF'
import json, time, urllib.request, concurrent.futures

URL = "http://10.72.100.35:7777/v1/chat/completions"
KEY = "sentosa-qwen3-embedding"

def call_one(i):
    body = json.dumps({
        "model": "lark",
        "messages": [{"role": "user", "content": f"Reply with exactly the number {i}."}],
        "max_tokens": 10,
        "temperature": 0.0,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    }).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode())
    return time.time() - t0, d["choices"][0]["message"]["content"]

# warmup
call_one(-1)

for workers in [1, 4, 8, 16]:
    n = 32
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(call_one, range(n)))
    dt = time.time() - t0
    print(f"LLM workers {workers}: {n} calls in {dt:.1f}s ({n/dt:.1f} req/s)", flush=True)
EOF
