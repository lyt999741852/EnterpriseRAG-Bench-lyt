set -euo pipefail
curl -fsS 'http://10.72.100.29:31920/enterprise-rag-qwen3-emb-v3-conan448/_search?size=1' \
  -H 'Content-Type: application/json' \
  -d '{"query":{"match_all":{}},"_source":{"excludes":["embedding"]}}' \
  | python -m json.tool | head -80
