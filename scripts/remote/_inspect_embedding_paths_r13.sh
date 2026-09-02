set -u
for p in /data06/embedding-models/multilingual-e5-large /data/guoenze/lark-ajie/models /opt/enterprise-rag-bench/model_cache/hub/models--BAAI--bge-small-en-v1.5; do
  echo "--- $p ---"
  if [ -e "$p" ]; then ls -ld "$p"; du -sh "$p" 2>/dev/null; find "$p" -maxdepth 2 -type f 2>/dev/null | head -30; else echo MISSING; fi
done
