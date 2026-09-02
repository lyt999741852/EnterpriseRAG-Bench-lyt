#!/usr/bin/env bash
set -euo pipefail

ROOT=/opt/enterprise-rag-bench
APP="$ROOT/app"
RUN="$APP/outputs/pageindex_stratified100_bge_rerank_cpu_20260813"
CONFIG="$APP/configs/eval_pageindex_stratified100_bge_rerank_cpu_20260813.yaml"
PYTHON=/root/anaconda3/envs/embedding_test/bin/python

: "${LARK_API_KEY:?LARK_API_KEY must be set}"
: "${EMBEDDING_API_KEY:?EMBEDDING_API_KEY must be set}"

mkdir -p "$RUN"
export PYTHONPATH="$APP:$ROOT/venv/lib/python3.10/site-packages"
export HF_HOME="$ROOT/model_cache"
export QUESTION_PARALLELISM="${QUESTION_PARALLELISM:-4}"
export EMBEDDING_PARALLELISM="${EMBEDDING_PARALLELISM:-4}"
export TOKENIZERS_PARALLELISM=false
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-8}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-8}"
cd "$APP"

if [ -f "$RUN/run.pid" ] && kill -0 "$(cat "$RUN/run.pid")" 2>/dev/null; then
  echo "ALREADY_RUNNING pid=$(cat "$RUN/run.pid")"
  exit 0
fi

if [ -s "$RUN/pipeline.log" ]; then
  if [ -f "$RUN/pipeline.serial_before_parallel.log" ]; then
    mv "$RUN/pipeline.log" "$RUN/pipeline.llm_parallel_before_embedding_pool.log"
  else
    mv "$RUN/pipeline.log" "$RUN/pipeline.serial_before_parallel.log"
  fi
fi

setsid nohup "$PYTHON" -u -m src.pipeline "$CONFIG" \
  > "$RUN/pipeline.log" 2>&1 < /dev/null &
echo $! > "$RUN/run.pid"
echo "STARTED pid=$(cat "$RUN/run.pid") run=$RUN"
