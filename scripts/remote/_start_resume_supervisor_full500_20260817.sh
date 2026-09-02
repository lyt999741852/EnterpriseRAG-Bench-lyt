#!/usr/bin/env bash
set -euo pipefail

RUN=/opt/enterprise-rag-bench/app/outputs/pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817
SUPERVISOR=/opt/enterprise-rag-bench/app/_resume_full500_bge_lowconcurrency_20260817.sh
mkdir -p "$RUN"
chmod +x "$SUPERVISOR"

if [ -f "$RUN/resume_supervisor.pid" ]; then
  pid=$(cat "$RUN/resume_supervisor.pid")
  if [ -r "/proc/$pid/cmdline" ] && tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q '_resume_full500_bge_lowconcurrency_20260817'; then
    echo "SUPERVISOR_ALREADY_RUNNING PID=$pid"
    exit 0
  fi
fi

nohup bash "$SUPERVISOR" > "$RUN/resume_supervisor.log" 2>&1 < /dev/null &
echo $! > "$RUN/resume_supervisor.pid"
echo "SUPERVISOR_STARTED PID=$(cat "$RUN/resume_supervisor.pid")"
