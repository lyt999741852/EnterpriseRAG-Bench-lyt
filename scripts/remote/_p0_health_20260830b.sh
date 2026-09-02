set -u
echo '=== LOCAL ES (mainline config) ==='
curl -sS --max-time 8 http://127.0.0.1:9200/_cluster/health 2>/dev/null | head -c 500; echo
curl -sS --max-time 8 http://127.0.0.1:9200/enterprise-rag-bge-small-v1/_count 2>/dev/null | head -c 500; echo
echo '=== REMOTE SERVICES AUTH STATUS ==='
auth_args=()
if [ -n "${HEALTH_API_KEY:-}" ]; then auth_args=(-H "Authorization: Bearer ${HEALTH_API_KEY}"); fi
for endpoint in http://10.72.55.209:7992/v1/models http://10.72.55.209:7993/v1/models; do
  printf '%s -> ' "$endpoint"
  curl -sS --connect-timeout 5 --max-time 10 "${auth_args[@]}" -o /dev/null -w '%{http_code}\n' "$endpoint" || true
done
echo '=== DPV4 ==='
curl -sS --max-time 6 http://127.0.0.1:18380/metrics 2>/dev/null | grep -E 'vllm:(num_requests_running|num_requests_waiting|kv_cache_usage_perc)' | head -20 || true
echo '=== GPU ==='
nvidia-smi --query-gpu=index,memory.total,memory.used,memory.free,utilization.gpu --format=csv,noheader,nounits 2>/dev/null || true
echo '=== BGE INDEX/MANIFEST ==='
for p in /opt/enterprise-rag-bench/app/.index_cache/full_es_bge_small /opt/enterprise-rag-bench/app/.index_cache/full_es_bge_small/manifest.sqlite3 /opt/enterprise-rag-bench/app/.pageindex_cache/balanced50_bge_rerank_question_only_llm_route_multiview_dpv4_20260828 /opt/enterprise-rag-bench/app/outputs/pageindex_balanced50_bge_rerank_question_only_llm_route_multiview_dpv4_20260828; do
  if [ -e "$p" ]; then
    echo "[$p]"
    ls -ld "$p"
    find "$p" -maxdepth 2 -type f 2>/dev/null | wc -l | awk '{print "files=" $1}'
  else
    echo "MISSING [$p]"
  fi
done
