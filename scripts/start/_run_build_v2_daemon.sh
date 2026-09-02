#!/usr/bin/env bash
# Detached build daemon for v2 (448+32 -> 10.72.100.29:31920), 2026-08-06.
# Restarts the build if it dies; safe because chunk_ids are deterministic
# and the backend skips already-indexed ids via _mget.
# Local archive copy; the live copy runs on the server:
#   setsid nohup bash /opt/enterprise-rag-bench/app/scripts/start/_run_build_v2_daemon.sh
set -u
ROOT="/opt/enterprise-rag-bench/app"
CONFIG="configs/full_es_qwen3_emb.yaml"
LOG="$ROOT/outputs/build_qwen3_emb_v2_20260806.log"
LOCK="$ROOT/outputs/q3emb_v2_build_daemon.lock"
MAX_RESTARTS=30

cd "$ROOT" || exit 1

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[$(date -Is)] daemon already running" >&2
  exit 0
fi

export EMBEDDING_API_KEY=123456
export TRANSFORMERS_OFFLINE=1

restart=0
while true; do
  if pgrep -f "src.build_es_index $CONFIG" >/dev/null 2>&1; then
    sleep 60
    continue
  fi
  if [ "$restart" -ge "$MAX_RESTARTS" ]; then
    echo "[$(date -Is)] restart limit reached" >> "$LOG"
    break
  fi
  restart=$((restart + 1))
  echo "[$(date -Is)] starting build (attempt $restart)" >> "$LOG"
  setsid nohup /root/anaconda3/envs/embedding_test/bin/python -u -m src.build_es_index "$CONFIG" \
    >> "$LOG" 2>&1 < /dev/null &
  sleep 60
done
