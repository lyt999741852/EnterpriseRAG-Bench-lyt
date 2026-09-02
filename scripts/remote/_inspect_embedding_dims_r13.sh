set -u
for d in /data06/embedding-models/acge_text_embedding /data06/embedding-models/piccolo-base-zh /data06/embedding-models/puff-large-v1 /data06/embedding-models/stella-mrl-large-zh-v3.5-1792d; do
  echo "--- $d ---"
  find "$d" -maxdepth 2 -type d -name '2_Dense*' -print 2>/dev/null
  find "$d" -maxdepth 2 -type f -path '*2_Dense*/*config.json' -o -path '*2_Dense*/config.json' 2>/dev/null | head -20
done
