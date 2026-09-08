#!/usr/bin/env bash
set -euo pipefail
APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/s4_full500_docaware_union_20260903"
mkdir -p "$RUN"
export TRANSFORMERS_OFFLINE=1
cd "$APP"
/root/anaconda3/envs/embedding_test/bin/python -u scripts/diag/run_s4_full500_fast_retrieval_20260903.py \
  --questions "$APP/questions.jsonl" \
  --ids-file "$APP/configs/s3_full500_question_ids_20260902.txt" \
  --output "$RUN/retrieval_report.json" --workers 8 \
  > "$RUN/retrieval.log" 2>&1
tail -n 5 "$RUN/retrieval.log"
