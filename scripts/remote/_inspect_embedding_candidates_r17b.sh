set -u
echo '=== HOST ==='
hostname
echo '=== CANDIDATE CONFIG FILES ==='
for p in /data01/embedding-models/Qwen3-Embedding-0.6B /data06/Conan-embedding-v1 /data06/gte_Qwen2-1.5B-instruct /data06/bge-m3 /data06/jina-colbert-v2 /data01/cihai/cihai-embedding-v3 /root/.cache/huggingface/hub/models--sentosa--jionglin-embedding /root/.cache/torch/sentence_transformers/sentosa_jionglin-embedding; do
  if [ -d "$p" ]; then
    echo "[$p]"
    du -sh "$p" 2>/dev/null || true
    find "$p" -maxdepth 3 -type f \( -name config.json -o -name modules.json -o -name sentence_bert_config.json \) 2>/dev/null | head -20
  fi
done
echo '=== CACHE SNAPSHOT NAMES ==='
find /data01/.cache/home/hub -maxdepth 1 -type d 2>/dev/null | grep -Ei 'models--(BAAI|TencentBAC|jinaai|intfloat|Alibaba|thenlper|sentence|nvidia)' | sed 's#^.*/models--##' | sort -u | head -100 || true
