set -u
for index in enterprise-rag-qwen3-emb-v1 enterprise-rag-qwen3-emb-v2 enterprise-rag-qwen3-emb-v3-conan448 enterprise-rag-qwen3-emb-v3-conan72; do
  echo "INDEX=$index"
  curl -fsS --max-time 15 "http://10.72.100.29:31920/$index/_count" || true
  echo
done
