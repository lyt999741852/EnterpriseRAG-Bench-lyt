#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
ROOT="$APP/conan_rag"
CONFIG=configs/eval_conan_current_replay100_20260820.yaml
RUN=conan_current_replay100_20260820
BLOCKER=erag-pageindex-ab50-20260820-r3.service
PYTHON=/root/anaconda3/envs/embedding_test/bin/python
EVAL_PYTHON=/root/anaconda3/bin/python
OFFICIAL_ROOT="$APP/EnterpriseRAG-Bench"

mkdir -p "$ROOT/outputs/$RUN"
exec > >(tee -a "$ROOT/outputs/$RUN/supervisor.log") 2>&1

echo "QUEUE_START $(date --iso-8601=seconds)"
while systemctl is-active --quiet "$BLOCKER"; do
  echo "WAIT_BGE $(date --iso-8601=seconds) unit=$BLOCKER"
  sleep 60
done

# Avoid overlapping a surviving child process or the BGE official judge even
# if the supervisor unit has just transitioned to inactive.
while pgrep -af 'src\.pipeline.*pageindex_ab50_semantic_consensus_20260820|metrics_based_eval.*pageindex_ab50_semantic_consensus_20260820' >/dev/null; do
  echo "WAIT_BGE_CHILD $(date --iso-8601=seconds)"
  sleep 60
done
echo "BGE_CLEAR $(date --iso-8601=seconds)"
sleep 120

cd "$ROOT"
: "${LARK_API_KEY:?LARK_API_KEY is required}"
: "${EMBEDDING_API_KEY:?EMBEDDING_API_KEY is required}"
export TRANSFORMERS_OFFLINE=1

"$PYTHON" - "$CONFIG" <<'PY'
import sys
from pathlib import Path

from src.conan_runner import validate_conan_config

path, config = validate_conan_config(Path(sys.argv[1]))
pipeline = config.get("pipeline", {})
assert pipeline.get("question_only") is True
assert pipeline.get("question_router", {}).get("enabled") is True
assert pipeline.get("read_existing_index") is True
assert pipeline.get("overwrite_index") is False
assert config.get("evaluation", {}).get("enabled") is False
question_ids = pipeline.get("question_ids", [])
assert len(question_ids) == 100 and len(set(question_ids)) == 100
print(f"PREFLIGHT_OK config={path} questions={len(question_ids)} question_only=true")
PY

echo $$ > "outputs/$RUN/supervisor.pid"
echo "PIPELINE_START $(date --iso-8601=seconds)"
"$PYTHON" -u -m src.conan_runner "$CONFIG" \
  > "outputs/$RUN/pipeline.log" 2>&1

"$PYTHON" - "outputs/$RUN/answers.jsonl" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
ids = [row.get("question_id") for row in rows]
allowed = {"question_id", "answer", "document_ids"}
assert len(rows) == 100 and len(set(ids)) == 100
assert all(set(row).issubset(allowed) for row in rows)
assert all(isinstance(row.get("answer"), str) for row in rows)
assert all(isinstance(row.get("document_ids"), list) for row in rows)
print("ANSWERS_CONTRACT_OK rows=100 unique_ids=100")
PY

echo "OFFICIAL_NO_CORRECTION_START $(date --iso-8601=seconds)"
export LLM_PROVIDER=openai
export LLM_API_KEY="$LARK_API_KEY"
export LLM_MODEL_NAME=lark
export CHEAP_LLM_MODEL_NAME=lark
export LLM_API_BASE=http://10.72.100.35:7777/v1
cd "$OFFICIAL_ROOT"
"$EVAL_PYTHON" -m src.scripts.answer_evaluation.metrics_based_eval \
  --questions-file "$APP/questions.jsonl" \
  --answers-file "$ROOT/outputs/$RUN/answers.jsonl" \
  --results-file "$ROOT/outputs/$RUN/results.json" \
  --parallelism 4 --no-correction --resume \
  > "$ROOT/outputs/$RUN/official_score.log" 2>&1

test -s "$ROOT/outputs/$RUN/results.json"
echo "COMPLETE $(date --iso-8601=seconds)"
