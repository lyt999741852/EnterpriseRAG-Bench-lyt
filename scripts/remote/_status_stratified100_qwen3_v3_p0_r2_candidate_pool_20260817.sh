#!/usr/bin/env bash
set -u
APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/pageindex_stratified100_qwen3_v3_p0_r2_candidate_pool_20260817"
if [ -f "$RUN/run.pid" ]; then
  pid=$(cat "$RUN/run.pid")
  echo "PID=$pid"
  ps -p "$pid" -o pid,stat,etime,%cpu,%mem,cmd --no-headers || true
fi
if [ -f "$RUN/answers.jsonl" ]; then
  echo "ANSWERS=$(wc -l < "$RUN/answers.jsonl")"
fi
echo "FILES"
find "$RUN" -maxdepth 1 -type f -printf '%f %s bytes\n' 2>/dev/null | sort
echo "LOG_TAIL"
tail -n 25 "$RUN/pipeline.log" 2>/dev/null || true
