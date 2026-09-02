set -u
echo '=== PYTHON ENVS ==='
for p in /opt/enterprise-rag-bench /root/anaconda3 /data01/miniconda3_64 /data01/qwen3-reranker-venv /data01/qwen3-reranker-vllm /data01/embedding-models; do
  [ -d "$p" ] && echo "[$p]" && find "$p" -maxdepth 4 -type f -path '*/bin/python*' -printf '%p\n' 2>/dev/null | head -20
done
echo '=== IMPORT CHECKS ==='
for py in /usr/bin/python3 /usr/local/bin/python3 /root/anaconda3/bin/python /data01/miniconda3_64/bin/python /data01/qwen3-reranker-venv/bin/python; do
  if [ -x "$py" ]; then
    echo "[$py]"
    "$py" -c 'import torch; print("torch",torch.__version__); import transformers; print("transformers",transformers.__version__); from transformers import AutoModel; print("automodel_ok")' 2>&1 | tail -8
  fi
done
