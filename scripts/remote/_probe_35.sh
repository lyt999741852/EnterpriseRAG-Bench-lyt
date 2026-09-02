#!/bin/bash
echo "=== probe 10.72.100.35 common ports ==="
for port in 22 80 443 7777 8000 8080 11434 7993 9200; do
  timeout 3 bash -c "echo > /dev/tcp/10.72.100.35/$port" 2>/dev/null && echo "port $port: OPEN" || echo "port $port: closed/filtered"
done
echo "=== LLM API health ==="
curl -s -m 10 'http://10.72.100.35:7777/v1/models' -H 'Authorization: Bearer sentosa-qwen3-embedding' | head -c 1000
echo
echo "=== LLM API chat quick test ==="
curl -s -m 30 -X POST 'http://10.72.100.35:7777/v1/chat/completions' -H 'Content-Type: application/json' -H 'Authorization: Bearer sentosa-qwen3-embedding' -d '{"model":"lark","messages":[{"role":"user","content":"reply OK"}],"max_tokens":5}' | head -c 400
echo
echo "=== embedding API on 35? ==="
curl -s -m 10 'http://10.72.100.35:7993/v1/models' -H 'Authorization: Bearer 123456' | head -c 600
echo
echo "=== try SSH banner ==="
timeout 5 bash -c "exec 3<>/dev/tcp/10.72.100.35/22 && head -c 100 <&3" 2>/dev/null || echo "ssh not reachable"
echo "=== ping ==="
ping -c 2 -W 2 10.72.100.35 2>&1 | tail -2
