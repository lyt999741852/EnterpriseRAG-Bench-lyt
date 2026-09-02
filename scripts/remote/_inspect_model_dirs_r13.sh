set -u
for d in /data /models /opt/enterprise-rag-bench /root/.cache/huggingface /root/.cache/torch/sentence_transformers; do
  echo "--- $d ---"
  if [ -d "$d" ]; then find "$d" -maxdepth 3 -mindepth 1 -type d 2>/dev/null | grep -Ei 'bge|embedding|e5|gte|jina|qwen|conan|model' | head -100; else echo missing; fi
done
echo '--- package/model config references ---'
grep -RIlE 'bge-small|bge-large|bge-m3|e5-large|gte|jina' /opt/enterprise-rag-bench/app /opt/enterprise-rag-bench/app/EnterpriseRAG-Bench 2>/dev/null | head -100
