#!/usr/bin/env bash
set -euo pipefail
cd /opt/enterprise-rag-bench/app
mkdir -p outputs/s3_20260902/s3_1
: "${DPV4_API_KEY:?DPV4_API_KEY is required}"
: "${EMBEDDING_API_KEY:?EMBEDDING_API_KEY is required}"
export TRANSFORMERS_OFFLINE=1
/root/anaconda3/envs/embedding_test/bin/python -u scripts/diag/run_s3_no_pageindex_agentic_20260902.py \
  --questions questions.jsonl \
  --ids-file configs/s3_ab50_question_ids_20260902.txt \
  --output outputs/s3_20260902/s3_1/s3_1_one_reflection.json \
  --answers outputs/s3_20260902/s3_1/answers.jsonl \
  --rounds 1 --workers 4 \
  > outputs/s3_20260902/s3_1/run.log 2>&1
