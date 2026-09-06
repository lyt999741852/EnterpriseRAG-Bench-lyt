#!/usr/bin/env bash
set -euo pipefail
APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/s4_full500_docaware_union_20260903"
: "${DPV4_API_KEY:?DPV4_API_KEY is required}"
: "${EMBEDDING_API_KEY:?EMBEDDING_API_KEY is required}"
export TRANSFORMERS_OFFLINE=1
cd "$APP"
mkdir -p "$RUN"
/root/anaconda3/envs/embedding_test/bin/python -u scripts/diag/run_s4_5_docaware_edge_generate_20260903.py \
  --questions "$APP/questions.jsonl" \
  --retrieval-report "$RUN/retrieval_report.json" \
  --answers "$RUN/answers.jsonl" \
  --generation-report "$RUN/generation_report.json" \
  --workers 4 --dpv4-base http://10.72.100.29:18380/v1 \
  > "$RUN/generation.log" 2>&1
export LLM_PROVIDER=openai
export LLM_API_KEY="$DPV4_API_KEY"
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
tail -n 10 "$RUN/official_score/score.log"
