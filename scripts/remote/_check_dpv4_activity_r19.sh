set -u
echo '=== PROCESS ==='
ps -eo pid,etime,%cpu,%mem,cmd | grep -E 'DeepSeek-V4-Flash-0731|deepseek-v4-flash' | grep -v grep || true
echo '=== PORT/HEALTH ==='
ss -lntp 2>/dev/null | grep -E ':18380\b' || true
for path in /health /v1/models /metrics; do
  echo "[$path]"
  curl -sS --max-time 5 "http://127.0.0.1:18380${path}" 2>/dev/null | head -80 || echo unavailable
done
echo '=== RECENT LOG HINTS ==='
find /tmp /var/log /opt/enterprise-rag-bench -maxdepth 4 -type f \( -iname '*deepseek*' -o -iname '*vllm*' \) -mmin -30 2>/dev/null | head -30 || true
