#!/usr/bin/env bash
set -u
RUN=/opt/enterprise-rag-bench/app/outputs/pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817
if [ -f "$RUN/resume_supervisor.pid" ]; then
  pid=$(cat "$RUN/resume_supervisor.pid")
  echo "SUPERVISOR_PID=$pid"
  ps -p "$pid" -o pid,stat,etime,%cpu,%mem,cmd --no-headers || true
fi
if [ -f "$RUN/run.pid" ]; then
  pid=$(cat "$RUN/run.pid")
  echo "PIPELINE_PID=$pid"
  ps -p "$pid" -o pid,stat,etime,%cpu,%mem,cmd --no-headers || true
fi
[ -f "$RUN/answers.jsonl" ] && echo "ANSWERS=$(wc -l < "$RUN/answers.jsonl")"
echo 'SUPERVISOR_LOG'
tail -n 10 "$RUN/resume_supervisor.log" 2>/dev/null || true
echo 'RESUME_LOG'
tail -n 10 "$RUN/pipeline_resume.log" 2>/dev/null || true
echo 'WATCH_LOG'
tail -n 10 "$RUN/watch_resume.log" 2>/dev/null || true
