#!/usr/bin/env bash
set -euo pipefail
: "${ERAG_APP_DIR:?ERAG_APP_DIR is required}"
APP="$ERAG_APP_DIR"
PYTHON_BIN="${PYTHON_BIN:-python}"
RUN="$APP/outputs/s3_repro_full500_20260903"
EVAL="$APP/EnterpriseRAG-Bench"
wc -l "$RUN/answers.jsonl"
sha256sum "$RUN/answers.jsonl" "$RUN/retrieval_report.json" "$RUN/official_score/results.json"
cd "$EVAL"
git rev-parse HEAD 2>/dev/null || echo "official_eval_git_commit=unavailable"
"$PYTHON_BIN" -m src.scripts.answer_evaluation.metrics_based_eval --help
