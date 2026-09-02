set -u
for d in /data06/embedding-models/acge_text_embedding /data06/embedding-models/multilingual-e5-large /data06/embedding-models/piccolo-base-zh /data06/embedding-models/puff-large-v1 /data06/embedding-models/stella-mrl-large-zh-v3.5-1792d; do
  echo "--- $d ---"
  du -sh "$d" 2>/dev/null
  for f in config.json sentence_bert_config.json modules.json README.md; do
    if [ -f "$d/$f" ]; then echo "[$f]"; sed -n '1,80p' "$d/$f"; fi
  done
done
