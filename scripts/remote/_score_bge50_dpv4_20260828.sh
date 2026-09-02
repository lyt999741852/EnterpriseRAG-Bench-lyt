#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/pageindex_balanced50_bge_rerank_question_only_llm_route_multiview_dpv4_20260828"

python - "$RUN/answers.jsonl" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
ids = {row.get("question_id") for row in rows}
print(f"answers={len(rows)} unique_ids={len(ids)}")
raise SystemExit(0 if len(rows) == 50 and len(ids) == 50 else 1)
PY

export LLM_PROVIDER=openai
: "${DPV4_API_KEY:?DPV4_API_KEY is required}"
export LLM_API_KEY="$DPV4_API_KEY"
export LLM_MODEL_NAME=deepseek-v4-flash
export CHEAP_LLM_MODEL_NAME=deepseek-v4-flash
export LLM_API_BASE=http://10.72.100.29:18380/v1
cd "$APP/EnterpriseRAG-Bench"
/root/anaconda3/bin/python -m src.scripts.answer_evaluation.metrics_based_eval \
  --questions-file "$APP/questions.jsonl" \
  --answers-file "$RUN/answers.jsonl" \
  --results-file "$RUN/results.json" \
  --parallelism 4 --no-correction --resume
