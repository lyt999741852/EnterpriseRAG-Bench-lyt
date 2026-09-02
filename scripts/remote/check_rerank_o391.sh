curl -sS -m 10 -o /tmp/rerank_health -w '%{http_code}\n' http://10.72.55.209:7992/health || true
cat /tmp/rerank_health 2>/dev/null || true
