#!/usr/bin/env bash
set -u
APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/pageindex_balanced50_bge_rerank_question_only_cpu_8192_20260814"
if [ -f "$RUN/run.pid" ]; then
  pid=$(cat "$RUN/run.pid")
  echo "PID=$pid"
  ps -p "$pid" -o pid=,stat=,etime=,%cpu=,%mem=,cmd= || true
fi
echo "FILES"
find "$RUN" -maxdepth 1 -type f -printf '%f %s bytes\n' 2>/dev/null | sort
echo "LOG_TAIL"
tail -n 25 "$RUN/pipeline.log" 2>/dev/null || true
