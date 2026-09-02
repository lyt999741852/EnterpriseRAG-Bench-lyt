#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/pageindex_stratified100_bge_rerank_cpu_20260813"
WATCH_PID_FILE="$RUN/scorer_watch.pid"
WATCH_LOG="$RUN/scorer_watch.log"

if [ -f "$WATCH_PID_FILE" ] && kill -0 "$(cat "$WATCH_PID_FILE")" 2>/dev/null; then
  echo "SCORER_ALREADY_WATCHING pid=$(cat "$WATCH_PID_FILE")"
  exit 0
fi

if [ -s "$WATCH_LOG" ]; then
  if [ -f "$RUN/scorer_watch.serial_before_parallel.log" ]; then
    mv "$WATCH_LOG" "$RUN/scorer_watch.llm_parallel_before_embedding_pool.log"
  else
    mv "$WATCH_LOG" "$RUN/scorer_watch.serial_before_parallel.log"
  fi
fi

setsid nohup bash -c '
  set -euo pipefail
  APP=/opt/enterprise-rag-bench/app
  RUN="$APP/outputs/pageindex_stratified100_bge_rerank_cpu_20260813"
  pipeline_pid=$(cat "$RUN/run.pid")
  echo "[$(date -Is)] waiting for pipeline pid=$pipeline_pid"
  while kill -0 "$pipeline_pid" 2>/dev/null; do sleep 30; done

  if ! /root/anaconda3/bin/python - "$RUN/answers.jsonl" <<"PY"
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []
ids = {row.get("question_id") for row in rows}
print(f"answers={len(rows)} unique_ids={len(ids)}")
raise SystemExit(0 if len(rows) == 100 and len(ids) == 100 else 1)
PY
  then
    echo "[$(date -Is)] pipeline ended without 100 complete answers; scorer skipped"
    exit 3
  fi

  export LLM_PROVIDER=openai
  export LLM_API_KEY=lark
  export LLM_MODEL_NAME=lark
  export CHEAP_LLM_MODEL_NAME=lark
  export LLM_API_BASE=http://10.72.100.35:7777/v1
  cd "$APP/EnterpriseRAG-Bench"
  echo "[$(date -Is)] starting official scorer"
  /root/anaconda3/bin/python -m src.scripts.answer_evaluation.metrics_based_eval \
    --questions-file "$APP/questions.jsonl" \
    --answers-file "$RUN/answers.jsonl" \
    --results-file "$RUN/results.json" \
    --parallelism 2 --no-correction --resume
  echo "[$(date -Is)] official scorer complete"
' > "$WATCH_LOG" 2>&1 < /dev/null &

echo $! > "$WATCH_PID_FILE"
echo "SCORER_WATCH_STARTED pid=$(cat "$WATCH_PID_FILE") log=$WATCH_LOG"
