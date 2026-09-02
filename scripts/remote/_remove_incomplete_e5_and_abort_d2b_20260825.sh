#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/semantic30_r4_d2b_e5_secondary_20260825"
CACHE="$APP/.index_cache/full_es_e5"
PIPELINE_PID=$(cat "$RUN/run.pid")

# Stop only this experiment's generator and its score watcher.
kill -TERM "$PIPELINE_PID" 2>/dev/null || true
for pid in $(pgrep -f 'while true; do.*semantic30_r4_d2b_e5_secondary_20260825' || true); do
  kill -TERM "$pid" 2>/dev/null || true
done
for _ in $(seq 1 20); do
  kill -0 "$PIPELINE_PID" 2>/dev/null || break
  sleep 1
done
if kill -0 "$PIPELINE_PID" 2>/dev/null; then
  kill -KILL "$PIPELINE_PID"
fi

# Delete only the explicitly verified incomplete index and its matching cache.
curl -fsS --max-time 60 -X DELETE \
  'http://127.0.0.1:9200/enterprise-rag-e5-large-v1'
rm -rf -- "$RUN" "$CACHE"

echo '--- VERIFY ---'
curl -sS --max-time 15 -o /dev/null -w 'e5_http=%{http_code}\n' \
  'http://127.0.0.1:9200/enterprise-rag-e5-large-v1/_count' || true
for path in "$RUN" "$CACHE"; do
  if [ -e "$path" ]; then echo "STILL_PRESENT $path"; exit 1; fi
done
test -d /data06/embedding-models/multilingual-e5-large
echo 'e5_model=preserved'
echo 'd2b=stopped_and_removed'
