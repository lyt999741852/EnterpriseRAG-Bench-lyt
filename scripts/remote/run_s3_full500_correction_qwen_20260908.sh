#!/usr/bin/env bash
set -euo pipefail

: "${ERAG_APP_DIR:?ERAG_APP_DIR is required}"
: "${LARK_API_BASE:?LARK_API_BASE is required}"
APP="$ERAG_APP_DIR"
PYTHON_BIN="${PYTHON_BIN:-python}"
RUN="$APP/outputs/s3_repro_full500_20260903"
EVAL="$APP/EnterpriseRAG-Bench"
SOURCE="$RUN/official_correction_dpv4_20260908"
OUT="$RUN/official_correction_qwen_20260908"
EXPECTED_ANSWERS_SHA256=37e042fa7c941c6a2666e42330f41f688282fe05812eae713c954f6350a3a08a

: "${LARK_API_KEY:?LARK_API_KEY is required}"
mkdir -p "$OUT"

actual_sha256="$(sha256sum "$RUN/answers.jsonl" | awk '{print $1}')"
if [[ "$actual_sha256" != "$EXPECTED_ANSWERS_SHA256" ]]; then
  echo "answers hash mismatch: expected=$EXPECTED_ANSWERS_SHA256 actual=$actual_sha256" >&2
  exit 1
fi

test -s "$SOURCE/bundle/questions.jsonl"
test -s "$SOURCE/bundle/uuid_index.json"
sha256sum "$RUN/answers.jsonl" "$RUN/retrieval_report.json" \
  "$SOURCE/bundle/questions.jsonl" "$SOURCE/bundle/uuid_index.json" \
  > "$OUT/input_sha256.txt"

export LLM_PROVIDER=openai
export LLM_API_KEY="$LARK_API_KEY"
export LLM_MODEL_NAME=lark
export CHEAP_LLM_MODEL_NAME=lark
export LLM_API_BASE="$LARK_API_BASE"

cd "$EVAL"
"$PYTHON_BIN" -u -m src.scripts.answer_evaluation.metrics_based_eval \
  --questions-file "$SOURCE/bundle/questions.jsonl" \
  --answers-file "$RUN/answers.jsonl" \
  --updated-questions-file "$OUT/questions_updated.jsonl" \
  --results-file "$OUT/results.json" \
  --uuid-index-cache-file "$SOURCE/bundle/uuid_index.json" \
  --parallelism 4 --resume > "$OUT/score.log" 2>&1

tail -n 12 "$OUT/score.log"
