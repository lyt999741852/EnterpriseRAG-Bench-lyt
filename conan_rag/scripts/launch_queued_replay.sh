#!/usr/bin/env bash
set -euo pipefail

ROOT=/opt/enterprise-rag-bench/app/conan_rag
RUN=conan_current_replay100_20260820
PID_FILE="$ROOT/outputs/$RUN/queue.pid"

mkdir -p "$ROOT/outputs/$RUN"
if test -f "$PID_FILE" && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "QUEUE_ALREADY_RUNNING pid=$(cat "$PID_FILE")"
  exit 0
fi

: "${LARK_API_KEY:?Export LARK_API_KEY before launching the queue}"
: "${EMBEDDING_API_KEY:?Export EMBEDDING_API_KEY before launching the queue}"

nohup bash "$ROOT/scripts/queue_current_replay_after_bge.sh" \
  >/dev/null 2>&1 < /dev/null &
queue_pid=$!
echo "$queue_pid" > "$PID_FILE"
echo "QUEUE_STARTED pid=$queue_pid"
