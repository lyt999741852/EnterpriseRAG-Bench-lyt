#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817"
PIPE_PID_FILE="$RUN/run.pid"

: "${LARK_API_KEY:?LARK_API_KEY is required}"

while [ -f "$PIPE_PID_FILE" ] && kill -0 "$(cat "$PIPE_PID_FILE")" 2>/dev/null; do
  sleep 60
done

if [ -f "$RUN/results.json" ]; then
  echo "SCORE_ALREADY_PRESENT"
  exit 0
fi

bash "$APP/_score_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817.sh" \
  > "$RUN/score.log" 2>&1
echo "SCORE_COMPLETE"
