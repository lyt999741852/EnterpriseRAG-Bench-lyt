#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/pageindex_stratified100_qwen3_v3_p0_r2_candidate_pool_20260817"
PIPE_PID_FILE="$RUN/run.pid"

: "${LARK_API_KEY:?LARK_API_KEY is required}"

while [ -f "$PIPE_PID_FILE" ] && kill -0 "$(cat "$PIPE_PID_FILE")" 2>/dev/null; do
  sleep 60
done

if [ -f "$RUN/results.json" ]; then
  echo "SCORE_ALREADY_PRESENT"
  exit 0
fi

bash "$APP/_score_stratified100_qwen3_v3_p0_r2_candidate_pool_20260817.sh" \
  > "$RUN/score.log" 2>&1
echo "SCORE_COMPLETE"
