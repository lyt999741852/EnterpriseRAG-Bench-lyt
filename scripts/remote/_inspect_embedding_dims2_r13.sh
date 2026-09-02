set -u
for f in /data06/embedding-models/acge_text_embedding/2_Dense/config.json /data06/embedding-models/puff-large-v1/2_Dense/config.json /data06/embedding-models/puff-large-v1/2_Dense_1792/config.json /data06/embedding-models/stella-mrl-large-zh-v3.5-1792d/2_Dense/config.json; do
  echo "--- $f ---"
  if [ -f "$f" ]; then cat "$f"; fi
done
