set -u
ES=http://10.72.55.201:31920
echo '--- target cluster ---'
curl -sS --max-time 20 "$ES/_cluster/health" | head -c 2000 || true
echo
echo '--- target indices ---'
curl -sS --max-time 30 "$ES/_cat/indices/enterprise-rag-*?format=json&h=index,docs.count,store.size,status" | head -c 12000 || true
echo
echo '--- target root ---'
curl -sS --max-time 20 "$ES/" | head -c 2000 || true
echo
echo '--- local model and resources ---'
du -sh /data06/embedding-models/bge-large-en-v1.5 2>/dev/null || true
python --version 2>&1 || true
nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total --format=csv,noheader 2>/dev/null || true
echo '--- existing R15 processes ---'
ps -eo pid,etime,pcpu,pmem,state,cmd | grep -E '[b]ge_large|[b]uild_es_index' || true
