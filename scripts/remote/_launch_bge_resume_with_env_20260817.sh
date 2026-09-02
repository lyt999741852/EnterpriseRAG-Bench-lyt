#!/usr/bin/env bash
set -euo pipefail

export LARK_API_KEY=lark
export EMBEDDING_API_KEY=123456
export TRANSFORMERS_OFFLINE=1
export QUESTION_PARALLELISM=1

APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817"
CONFIG="$APP/configs/eval_pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817.yaml"

if [ -f "$RUN/run.pid" ]; then
  pid=$(cat "$RUN/run.pid")
  if [ -r "/proc/$pid/cmdline" ] && tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q 'src.pipeline.*full500_bge_rerank_question_only_llm_route_multiview_p0_20260817'; then
    echo "ALREADY_RUNNING PID=$pid"
    exit 0
  fi
fi

cd "$APP"
nohup /root/anaconda3/envs/embedding_test/bin/python -u -m src.pipeline \
  "$CONFIG" >> "$RUN/pipeline_resume.log" 2>&1 < /dev/null &
echo $! > "$RUN/run.pid"
nohup bash "$APP/_watch_score_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817.sh" \
  >> "$RUN/watch_resume.log" 2>&1 < /dev/null &
echo "RESUME_STARTED PID=$(cat "$RUN/run.pid") QUESTION_PARALLELISM=$QUESTION_PARALLELISM"
