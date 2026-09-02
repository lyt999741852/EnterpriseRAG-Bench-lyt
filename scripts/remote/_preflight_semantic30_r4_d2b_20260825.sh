set -u
echo '--- QWEN ES INDEX ---'
curl -fsS --max-time 15 'http://10.72.100.29:31920/enterprise-rag-qwen3-emb-v2/_count' || true
echo
echo '--- QWEN EMBEDDING API ---'
curl -fsS --max-time 30 'http://10.72.55.209:7993/v1/embeddings' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer 123456' \
  -d '{"model":"embedding","input":"enterprise semantic retrieval health check"}' \
  | /root/anaconda3/bin/python -c 'import json,sys; d=json.load(sys.stdin); print({"vectors":len(d.get("data",[])),"dimension":len(d.get("data",[{}])[0].get("embedding",[])),"error":d.get("error")})' || true
