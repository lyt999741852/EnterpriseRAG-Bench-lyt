#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817"
CONFIG="$APP/configs/eval_pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817.yaml"

mkdir -p "$RUN"

while true; do
  if [ -f "$RUN/run.pid" ]; then
    pid=$(cat "$RUN/run.pid")
    if [ -r "/proc/$pid/cmdline" ] && tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q 'src.pipeline.*full500_bge_rerank_question_only_llm_route_multiview_p0_20260817'; then
      echo "ALREADY_RUNNING PID=$pid"
      exit 0
    fi
  fi

  llm_status=$(curl -sS --connect-timeout 5 --max-time 15 -o /dev/null -w '%{http_code}' http://10.72.100.35:7777/v1/models || true)
  rerank_status=$(curl -sS --connect-timeout 5 --max-time 15 -o /dev/null -w '%{http_code}' http://10.72.55.209:7992/v1/models || true)
  echo "$(date -Is) llm=$llm_status rerank=$rerank_status"

  if [ "$llm_status" != "000" ] && [ "$rerank_status" != "000" ]; then
    : "${LARK_API_KEY:?LARK_API_KEY is required}"
    : "${EMBEDDING_API_KEY:?EMBEDDING_API_KEY is required}"
    export TRANSFORMERS_OFFLINE=1
    export QUESTION_PARALLELISM=1
    cd "$APP"
    nohup /root/anaconda3/envs/embedding_test/bin/python -u -m src.pipeline \
      "$CONFIG" \
      >> "$RUN/pipeline_resume.log" 2>&1 < /dev/null &
    echo $! > "$RUN/run.pid"
    nohup bash "$APP/_watch_score_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817.sh" \
      >> "$RUN/watch_resume.log" 2>&1 < /dev/null &
    echo "RESUME_LAUNCHED PID=$(cat "$RUN/run.pid") QUESTION_PARALLELISM=1"
    exit 0
  fi

  sleep 60
done
