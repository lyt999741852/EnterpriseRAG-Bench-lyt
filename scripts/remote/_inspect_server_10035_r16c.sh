set -u
echo '=== identity ==='
hostname
date
echo '=== candidate model directories ==='
for d in /data /data01 /data06 /model /models /opt/ollama/models; do
  if [ -e "$d" ]; then
    echo "[$d]"
    find "$d" -maxdepth 3 -type d 2>/dev/null | grep -Ei 'bge|embed|e5|gte|jina|puff|stella|acge|rerank' | head -60 || true
  fi
done
echo '=== filtered containers ==='
docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep -Ei 'embed|bge|rerank|ollama|vllm|qwen|seed|lark' | head -100 || true
echo '=== listening ports ==='
ss -lntp 2>/dev/null | head -120 || true
