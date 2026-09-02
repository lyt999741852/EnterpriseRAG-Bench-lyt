set -u
BASE=https://huggingface.co/BAAI/bge-large-en-v1.5/resolve/main
DEST=/data06/embedding-models/bge-large-en-v1.5
mkdir -p "$DEST/1_Pooling"
for f in config.json tokenizer.json tokenizer_config.json vocab.txt special_tokens_map.json modules.json sentence_bert_config.json; do
  if [ ! -s "$DEST/$f" ]; then
    curl -4 -fL --retry 3 --connect-timeout 20 --max-time 120 "$BASE/$f?download=true" -o "$DEST/$f"
  fi
done
if [ ! -s "$DEST/1_Pooling/config.json" ]; then
  curl -4 -fL --retry 3 --connect-timeout 20 --max-time 120 "$BASE/1_Pooling/config.json?download=true" -o "$DEST/1_Pooling/config.json"
fi
find -L "$DEST" -maxdepth 2 -type f -printf '%f %s\\n' | sort
