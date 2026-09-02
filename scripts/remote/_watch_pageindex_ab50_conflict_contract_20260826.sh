#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
NAME=pageindex_ab50_semantic_conflict_contract_20260826
RUN="$APP/outputs/$NAME"
CONFIG="$APP/configs/eval_$NAME.yaml"

while pgrep -f "src.pipeline.*$CONFIG" >/dev/null 2>&1; do
  sleep 30
done

if [ -s "$RUN/answers.jsonl" ] && [ "$(wc -l < "$RUN/answers.jsonl")" -eq 50 ] && [ ! -f "$RUN/results.json" ]; then
  export LLM_PROVIDER=openai
  export LLM_API_KEY="${LARK_API_KEY:?LARK_API_KEY is required}"
  export LLM_MODEL_NAME=lark
  export CHEAP_LLM_MODEL_NAME=lark
  export LLM_API_BASE=http://10.72.100.35:7777/v1
  cd "$APP/EnterpriseRAG-Bench"
  /root/anaconda3/bin/python -u -m src.scripts.answer_evaluation.metrics_based_eval \
    --questions-file "$APP/questions.jsonl" \
    --answers-file "$RUN/answers.jsonl" \
    --results-file "$RUN/results.json" \
    --parallelism 4 --no-correction --resume > "$RUN/score.log" 2>&1
fi

if [ -f "$APP/src/generator.py.a32_conflict_contract.bak" ]; then
  cd "$APP"
  python scripts/remote/apply_semantic_a32_conflict_contract.py rollback > "$RUN/rollback.log" 2>&1
fi
