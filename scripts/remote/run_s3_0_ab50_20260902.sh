#!/usr/bin/env bash
set -euo pipefail
cd /opt/enterprise-rag-bench/app
mkdir -p outputs/s3_20260902
export TRANSFORMERS_OFFLINE=1
/root/anaconda3/envs/embedding_test/bin/python -u scripts/diag/run_s3_no_pageindex_agentic_20260902.py \
  --questions questions.jsonl \
  --ids-file configs/s3_ab50_question_ids_20260902.txt \
  --output outputs/s3_20260902/s3_0_four_lane_recall.json \
  --rounds 0 --workers 4 \
  > outputs/s3_20260902/s3_0_four_lane_recall.log 2>&1
