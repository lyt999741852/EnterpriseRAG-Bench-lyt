ps aux | grep -E 'rerank|7992' | grep -v grep || true
curl -sS -m 10 http://10.72.55.209:7992/v1/models || true
