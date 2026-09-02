set -u
echo '=== HOST ==='
hostname
echo '=== GPU MEMORY/UTILIZATION ==='
nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu --format=csv,noheader,nounits 2>/dev/null || true
echo '=== GPU PROCESSES ==='
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv,noheader 2>/dev/null | head -80 || true
echo '=== VLLM PROCESSES ==='
ps -eo pid,etime,%cpu,cmd | grep -E 'vllm serve|vllm.entrypoints' | grep -v grep | head -80 || true
echo '=== DPV4 ACTIVITY (if present) ==='
curl -sS --max-time 4 http://127.0.0.1:18380/metrics 2>/dev/null | grep -E 'vllm:(num_requests_running|num_requests_waiting|kv_cache_usage_perc)' | head -20 || true
