#!/usr/bin/env bash
set -euo pipefail
APP=/opt/enterprise-rag-bench/app
RUN=$APP/outputs/s3_20260902/full500_top10
while true; do
  if [ -f "$RUN/answers.jsonl" ] && [ "$(wc -l < "$RUN/answers.jsonl")" -ge 500 ] && [ -f "$RUN/retrieval_report.json" ]; then
    break
  fi
  sleep 30
done
export LLM_PROVIDER=openai
export LLM_API_KEY="${DPV4_API_KEY:?DPV4_API_KEY is required}"
export LLM_MODEL_NAME=deepseek-v4-flash
export CHEAP_LLM_MODEL_NAME=deepseek-v4-flash
export LLM_API_BASE=http://10.72.100.29:18380/v1
cd "$APP/EnterpriseRAG-Bench"
mkdir -p "$RUN/official_score"
/root/anaconda3/bin/python -u -m src.scripts.answer_evaluation.metrics_based_eval \
  --questions-file "$APP/questions.jsonl" \
  --answers-file "$RUN/answers.jsonl" \
  --results-file "$RUN/official_score/results.json" \
  --parallelism 8 --no-correction --resume \
  > "$RUN/official_score/score.log" 2>&1
