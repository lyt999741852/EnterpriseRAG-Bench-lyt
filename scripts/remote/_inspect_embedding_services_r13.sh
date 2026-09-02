set -u
echo '--- Conan embedding models ---'
curl -sS -w '\nHTTP %{http_code}\n' http://10.72.55.209:7993/v1/models \
  -H 'Authorization: Bearer 123456' | head -c 12000
echo
echo '--- reranker models ---'
curl -sS -w '\nHTTP %{http_code}\n' http://10.72.55.209:7992/v1/models \
  -H 'Authorization: Bearer 123456' | head -c 12000
echo
echo '--- local model/cache candidates ---'
find /opt/enterprise-rag-bench /root/.cache /root/.cache/huggingface -maxdepth 5 -type f \( -name 'config.json' -o -name 'modules.json' -o -name 'sentence_bert_config.json' \) 2>/dev/null \
  | grep -Ei 'bge|embedding|e5|gte|jina|m3|qwen' | head -80
