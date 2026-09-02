set -u
echo '=== HOST ==='
hostname
echo '=== PROCESS/SERVICE HINTS ==='
ps -eo pid,cmd --sort=cmd 2>/dev/null | grep -Ei 'embedding|embed|bge|conan|e5|gte|jina|cihai|sentence.transformers|text.embeddings|tei|vllm' | grep -v grep | head -120 || true
echo '=== MODEL DIRECTORIES ==='
for d in /data /data01 /data06 /opt /model /models /root/.cache/huggingface /root/.cache/torch; do
  if [ -d "$d" ]; then
    echo "[$d]"
    find "$d" -maxdepth 5 -type d 2>/dev/null | grep -Ei 'bge|embed|embedding|conan|e5-|gte|jina|cihai|stella|puff|acge|text2vec|m3e|sentence' | head -160 || true
  fi
done
echo '=== RELEVANT CONTAINERS ==='
docker ps --format '{{.Names}} {{.Image}} {{.Ports}}' 2>/dev/null | grep -Ei 'embed|bge|conan|rerank|tei|inference|vllm|cihai' | head -120 || true
