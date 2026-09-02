set -u
for p in /data01/cihai/cihai-embedding-v3 /data01/embedding-models /data06; do
  if [ -d "$p" ]; then
    echo "[$p]"
    du -sh "$p" 2>/dev/null || true
  fi
done
find /data01/cihai/cihai-embedding-v3 -maxdepth 3 -type f 2>/dev/null | head -80 || true
for f in /data01/cihai/cihai-embedding-v3/config.json /data01/cihai/cihai-embedding-v3/1_Pooling/config.json /data01/cihai/cihai-embedding-v3/modules.json /data01/cihai/cihai-embedding-v3/sentence_bert_config.json; do
  if [ -f "$f" ]; then echo "[$f]"; grep -E 'hidden_size|projection_dim|in_features|out_features|word_embedding_dimension|pooling_mode|model_type|max_seq_length' "$f" | head -40 || true; fi
done
