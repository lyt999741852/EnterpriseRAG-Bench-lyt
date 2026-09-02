set -u
echo '--- GPU ---'
nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu --format=csv,noheader 2>/dev/null || true
echo '--- memory/disk ---'
free -h 2>/dev/null || true
df -h /data06 /opt 2>/dev/null || true
