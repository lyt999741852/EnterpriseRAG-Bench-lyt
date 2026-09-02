set -u
for root in /data06/embedding-models /data/embedding-models /data/rerank-models /opt/enterprise-rag-bench/model_cache/hub /root/.cache/huggingface/hub; do
  echo "--- $root ---"
  if [ -d "$root" ]; then find "$root" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | sort; else echo MISSING; fi
done
