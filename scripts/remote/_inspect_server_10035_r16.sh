set -u
echo '--- identity ---'
hostname 2>/dev/null || true
uname -a 2>/dev/null || true
echo '--- cpu/memory ---'
nproc 2>/dev/null || true
free -h 2>/dev/null | head -5 || true
echo '--- disks ---'
df -h 2>/dev/null | head -20 || true
echo '--- gpu ---'
nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total --format=csv,noheader 2>/dev/null || echo NO_NVIDIA_SMI
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv,noheader 2>/dev/null | head -30 || true
echo '--- model/server processes ---'
ps -eo pid,etime,pcpu,pmem,state,cmd 2>/dev/null | grep -E '[v]llm|[o]llama|[t]ext-generation|[e]mbedding|[s]entence|[d]eepseek|[q]wen|[t]riton' | head -80 || true
echo '--- listening ports ---'
ss -lntp 2>/dev/null | grep -E ':(7777|8000|8001|8080|8192|9000|11434|18380|7992|7993)\\b' || true
echo '--- candidate model directories ---'
for d in /data /data06 /models /opt /root/.cache/huggingface /root/.cache/torch; do
  if [ -d "$d" ]; then
    echo "[$d]"
    find "$d" -maxdepth 4 -type d 2>/dev/null | grep -Ei 'bge|embedding|e5|gte|jina|puff|stella|acge|model' | head -80 || true
  fi
done
