#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/semantic30_r4_d2b_e5_secondary_20260825"
CACHE="$APP/.index_cache/full_es_e5"
WATCHER_PID=64316

# PID is accepted only if it is still the D2b score watcher observed during
# the preflight; never kill a reused PID.
if [ -r "/proc/$WATCHER_PID/cmdline" ]; then
  cmd=$(tr '\0' ' ' < "/proc/$WATCHER_PID/cmdline")
  case "$cmd" in
    *semantic30_r4_d2b_e5_secondary_20260825*) kill -TERM "$WATCHER_PID" ;;
    *) echo "watcher_pid_reused_or_unrelated=$WATCHER_PID" ;;
  esac
fi

curl -fsS --max-time 60 -X DELETE \
  'http://127.0.0.1:9200/enterprise-rag-e5-large-v1'

for path in "$RUN" "$CACHE"; do
  [ "$(realpath "$path")" = "$path" ]
done
rm -rf -- "$RUN" "$CACHE"

echo '--- VERIFY ---'
if [ -e "$RUN" ] || [ -e "$CACHE" ]; then
  echo 'ERROR: local artifact still present'
  exit 1
fi
curl -sS --max-time 15 -o /dev/null -w 'e5_index_http=%{http_code}\n' \
  'http://127.0.0.1:9200/enterprise-rag-e5-large-v1/_count' || true
if [ -r "/proc/$WATCHER_PID/cmdline" ]; then
  echo "ERROR: watcher still present=$WATCHER_PID"
  exit 1
fi
test -d /data06/embedding-models/multilingual-e5-large
echo 'e5_model=preserved'
echo 'cleanup=complete'
