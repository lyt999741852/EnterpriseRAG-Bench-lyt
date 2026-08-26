#!/usr/bin/env bash
# Launch the B1 smoke run; credentials are inherited from the caller's env.
set -euo pipefail

: "${LARK_API_KEY:?LARK_API_KEY must be set}"
: "${EMBEDDING_API_KEY:?EMBEDDING_API_KEY must be set}"

APP=/opt/enterprise-rag-bench/app
NAME=b1_basic_checklist_smoke10_20260825
RUN="$APP/outputs/$NAME"
CONFIG="$APP/configs/eval_b1_basic_checklist_smoke10_20260825.yaml"

mkdir -p "$RUN"
if [ -f "$RUN/run.pid" ] && kill -0 "$(cat "$RUN/run.pid")" 2>/dev/null; then
  echo "ALREADY_RUNNING PID=$(cat "$RUN/run.pid")"
  exit 0
fi

cd "$APP"
nohup /root/anaconda3/envs/embedding_test/bin/python -u -m src.pipeline "$CONFIG" \
  > "$RUN/pipeline.log" 2>&1 < /dev/null &
echo $! > "$RUN/run.pid"
echo "PIPELINE_PID=$(cat "$RUN/run.pid")"
echo "RUN=$RUN"
