#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
RUN=pageindex_smoke3_qwen3_v3_p0_chain_20260816
cd "$APP"
mkdir -p "outputs/$RUN"

if [ -f "outputs/$RUN/run.pid" ] && kill -0 "$(cat "outputs/$RUN/run.pid")" 2>/dev/null; then
  echo "ALREADY_RUNNING PID=$(cat "outputs/$RUN/run.pid")"
  exit 0
fi

: "${LARK_API_KEY:?LARK_API_KEY is required}"
: "${EMBEDDING_API_KEY:?EMBEDDING_API_KEY is required}"
export TRANSFORMERS_OFFLINE=1
export QUESTION_PARALLELISM=3

nohup /root/anaconda3/envs/embedding_test/bin/python -u -m src.pipeline \
  configs/eval_pageindex_smoke3_qwen3_v3_p0_chain_20260816.yaml \
  > "outputs/$RUN/pipeline.log" 2>&1 < /dev/null &
echo $! > "outputs/$RUN/run.pid"
echo "PID=$(cat "outputs/$RUN/run.pid")"
sleep 2
tail -n 25 "outputs/$RUN/pipeline.log" || true
