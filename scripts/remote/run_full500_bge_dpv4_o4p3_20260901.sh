#!/usr/bin/env bash
set -euo pipefail
APP=/opt/enterprise-rag-bench/app
RUN=pageindex_full500_bge_dpv4_o4p3_20260901
cd "$APP"
mkdir -p "outputs/$RUN"
if [ -f "outputs/$RUN/run.pid" ] && kill -0 "$(cat "outputs/$RUN/run.pid")" 2>/dev/null; then
  echo "ALREADY_RUNNING PID=$(cat "outputs/$RUN/run.pid")"
  exit 0
fi
: "${DPV4_API_KEY:?DPV4_API_KEY is required}"
: "${EMBEDDING_API_KEY:?EMBEDDING_API_KEY is required}"
export TRANSFORMERS_OFFLINE=1
export QUESTION_PARALLELISM=4
nohup /root/anaconda3/envs/embedding_test/bin/python -u -m src.pipeline \
  configs/eval_pageindex_full500_bge_dpv4_o4p3_20260901.yaml \
  > "outputs/$RUN/pipeline.log" 2>&1 < /dev/null &
echo $! > "outputs/$RUN/run.pid"
echo "PID=$(cat "outputs/$RUN/run.pid")"
