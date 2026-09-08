#!/usr/bin/env bash
set -euo pipefail
: "${ERAG_APP_DIR:?ERAG_APP_DIR is required}"
: "${DPV4_API_BASE:?DPV4_API_BASE is required}"
APP="$ERAG_APP_DIR"
PYTHON_BIN="${PYTHON_BIN:-python}"
RUN="$APP/outputs/s3_repro_full500_20260903"
EVAL="$APP/EnterpriseRAG-Bench"
CORR="$RUN/official_correction_dpv4_20260908"
: "${DPV4_API_KEY:?DPV4_API_KEY is required}"
mkdir -p "$CORR/bundle" "$CORR"
sha256sum "$RUN/answers.jsonl" "$RUN/retrieval_report.json" \
  "$RUN/official_score/results.json" > "$CORR/input_sha256.txt"
cd "$APP"
"$PYTHON_BIN" -u scripts/remote/_prepare_official_correction_bundle.py \
  --questions-file "$APP/questions.jsonl" \
  --answers-file "$RUN/answers.jsonl" \
  --official-root "$EVAL" \
  --bundle-dir "$CORR/bundle" \
  --workers 8 > "$CORR/prepare.log" 2>&1
export LLM_PROVIDER=openai
export LLM_API_KEY="$DPV4_API_KEY"
export LLM_MODEL_NAME=deepseek-v4-flash
export CHEAP_LLM_MODEL_NAME=deepseek-v4-flash
export LLM_API_BASE="$DPV4_API_BASE"
cd "$EVAL"
"$PYTHON_BIN" -u -m src.scripts.answer_evaluation.metrics_based_eval \
  --questions-file "$CORR/bundle/questions.jsonl" \
  --answers-file "$RUN/answers.jsonl" \
  --updated-questions-file "$CORR/questions_updated.jsonl" \
  --results-file "$CORR/results.json" \
  --uuid-index-cache-file "$CORR/bundle/uuid_index.json" \
  --parallelism 8 --resume > "$CORR/score.log" 2>&1
tail -n 12 "$CORR/score.log"
