#!/usr/bin/env bash
set -euo pipefail
APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/pageindex_o1_original_reserve_smoke20_20260831"
python - "$RUN/answers.jsonl" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
ids = {row.get("question_id") for row in rows}
print(f"answers={len(rows)} unique_ids={len(ids)}")
raise SystemExit(0 if len(rows) == 20 and len(ids) == 20 else 1)
PY
: "${DPV4_API_KEY:?DPV4_API_KEY is required}"
export LLM_PROVIDER=openai
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
