set -u
echo '--- E5 INDEX ---'
curl -fsS --max-time 15 'http://127.0.0.1:9200/enterprise-rag-e5-large-v1/_count' || true
echo
echo '--- E5 ASSETS ---'
test -d /data06/embedding-models/multilingual-e5-large && echo MODEL_PRESENT || echo MODEL_MISSING
test -f /opt/enterprise-rag-bench/app/.index_cache/full_es_e5/manifest.sqlite3 && echo MANIFEST_PRESENT || echo MANIFEST_MISSING
echo '--- GPU ---'
nvidia-smi --query-gpu=index,name,memory.free,utilization.gpu --format=csv,noheader 2>/dev/null || true
