#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/pageindex_balanced50_bge_rerank_question_only_llm_route_multiview_20260814/official_correction"
SCORE_SCRIPT="$APP/scripts/remote/_score_question_only_bge_llm_route_multiview_correction_20260814.sh"

mkdir -p "$RUN"
if [[ -f "$RUN/score.pid" ]] && kill -0 "$(cat "$RUN/score.pid")" 2>/dev/null; then
  echo "ALREADY_RUNNING PID=$(cat "$RUN/score.pid")"
  exit 0
fi

nohup bash "$SCORE_SCRIPT" > "$RUN/score.log" 2>&1 < /dev/null &
echo $! > "$RUN/score.pid"
echo "PID=$(cat "$RUN/score.pid")"
sleep 2
tail -n 20 "$RUN/score.log" || true
