#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
NAME=pageindex_r11b_structured_query_smoke_r2_20260827
RUN="$APP/outputs/$NAME"
CONFIG="$APP/configs/eval_$NAME.yaml"
PYTHON=/root/anaconda3/envs/embedding_test/bin/python

cd "$APP"
"$PYTHON" scripts/remote/apply_r11b_structured_query_union.py apply
"$PYTHON" -m py_compile src/pipeline.py
mkdir -p "$RUN"

if [ -f "$RUN/run.pid" ] && kill -0 "$(cat "$RUN/run.pid")" 2>/dev/null; then
  echo "ALREADY_RUNNING PID=$(cat "$RUN/run.pid")"
  exit 0
fi

export LARK_API_KEY=lark
export EMBEDDING_API_KEY=123456
export TRANSFORMERS_OFFLINE=1
export QUESTION_PARALLELISM=2

nohup "$PYTHON" -u -m src.pipeline "$CONFIG" > "$RUN/pipeline.log" 2>&1 < /dev/null &
echo $! > "$RUN/run.pid"
echo "PIPELINE_PID=$(cat "$RUN/run.pid")"
echo "RUN=$RUN"
