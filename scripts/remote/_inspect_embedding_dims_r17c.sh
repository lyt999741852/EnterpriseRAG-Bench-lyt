set -u
for f in \
 /data01/embedding-models/Qwen3-Embedding-0.6B/config.json \
 /data01/embedding-models/Qwen3-Embedding-0.6B/1_Pooling/config.json \
 /data06/Conan-embedding-v1/config.json \
 /data06/Conan-embedding-v1/1_Pooling/config.json \
 /data06/Conan-embedding-v1/2_Dense/config.json \
 /data06/gte_Qwen2-1.5B-instruct/config.json \
 /data06/gte_Qwen2-1.5B-instruct/1_Pooling/config.json; do
  if [ -f "$f" ]; then
    echo "[$f]"
    grep -E 'hidden_size|projection_dim|in_features|out_features|word_embedding_dimension|pooling_mode|do_lower_case|max_seq_length' "$f" | head -30 || true
  fi
done
echo '=== BGE M3 CACHE SNAPSHOT ==='
find /data01/.cache/home/hub/models--BAAI--bge-m3/snapshots -maxdepth 2 -type f 2>/dev/null | head -20 || true
