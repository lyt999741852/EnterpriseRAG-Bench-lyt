#!/usr/bin/env bash
set -euo pipefail
APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/s3_repro_full500_20260903"
mkdir -p "$RUN"
: "${DPV4_API_KEY:?DPV4_API_KEY is required}"
: "${S3_DPV4_BASE:=http://10.72.100.29:18380/v1}"
: "${EMBEDDING_API_KEY:?EMBEDDING_API_KEY is required}"
export TRANSFORMERS_OFFLINE=1
cd "$APP"
/root/anaconda3/envs/embedding_test/bin/python -u scripts/diag/run_s3_no_pageindex_agentic_20260902.py \
  --questions "$APP/questions.jsonl" \
  --ids-file "$APP/configs/s3_full500_question_ids_20260902.txt" \
  --output "$RUN/retrieval_report.json" \
  --answers "$RUN/answers.jsonl" \
  --rounds 1 --workers 4 \
  > "$RUN/run.log" 2>&1
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
