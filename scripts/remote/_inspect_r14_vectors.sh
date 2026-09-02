set -u
curl -sS -XPOST http://127.0.0.1:9200/enterprise-rag-bge-large-r14-candidates50-k40/_search \
  -H 'Content-Type: application/json' \
  -d '{"size":3,"query":{"match_all":{}},"_source":["chunk_id","doc_id","embedding"]}' \
  | head -c 4000
echo
