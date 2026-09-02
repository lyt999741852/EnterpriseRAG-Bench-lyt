#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
NAME=semantic30_r4_d2b_e5_secondary_20260825
RUN="$APP/outputs/$NAME"
CONFIG="$APP/configs/eval_$NAME.yaml"

mkdir -p "$RUN"
if [ -f "$RUN/run.pid" ] && kill -0 "$(cat "$RUN/run.pid")" 2>/dev/null; then
  echo "ALREADY_RUNNING PID=$(cat "$RUN/run.pid")"
  exit 0
fi

export LARK_API_KEY=lark
export EMBEDDING_API_KEY=123456
export TRANSFORMERS_OFFLINE=1
export QUESTION_PARALLELISM=2
cd "$APP"
nohup /root/anaconda3/envs/embedding_test/bin/python -u -m src.pipeline "$CONFIG" > "$RUN/pipeline.log" 2>&1 < /dev/null &
echo $! > "$RUN/run.pid"

nohup bash -c '
  set -u
  while true; do
    if [ -s "$0/answers.jsonl" ] && [ "$(wc -l < "$0/answers.jsonl")" -ge 30 ]; then
      export LLM_PROVIDER=openai
      export LLM_API_KEY="$LARK_API_KEY"
      export LLM_MODEL_NAME=lark
      export CHEAP_LLM_MODEL_NAME=lark
      export LLM_API_BASE=http://10.72.100.35:7777/v1
      cd "$1/EnterpriseRAG-Bench"
      /root/anaconda3/bin/python -m src.scripts.answer_evaluation.metrics_based_eval \
        --questions-file "$1/questions.jsonl" \
        --answers-file "$0/answers.jsonl" \
        --results-file "$0/results.json" \
        --parallelism 2 --no-correction --resume > "$0/score.log" 2>&1
      break
    fi
    sleep 20
  done
' "$RUN" "$APP" > "$RUN/score_watch.log" 2>&1 < /dev/null &

echo "PIPELINE_PID=$(cat "$RUN/run.pid")"
echo "RUN=$RUN"
