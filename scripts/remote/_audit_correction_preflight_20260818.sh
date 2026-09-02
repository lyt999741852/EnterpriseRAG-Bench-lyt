#!/usr/bin/env bash
set -u
APP=/opt/enterprise-rag-bench/app
EVAL="$APP/EnterpriseRAG-Bench"
RUN="$APP/outputs/pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817"
echo 'CORRECTION_INPUTS'
for f in "$EVAL/generated_data/uuid_index.json" "$EVAL/questions.jsonl" "$RUN/answers.jsonl" "$EVAL/src/utils/eval_utils.py" "$EVAL/src/scripts/answer_evaluation/metrics_based_eval.py"; do
  if [ -f "$f" ]; then
    stat -c '%n %s bytes' "$f"
  else
    echo "MISSING $f"
  fi
done
echo 'UUID_INDEX'
python - "$EVAL/generated_data/uuid_index.json" "$RUN/answers.jsonl" <<'PY'
import json
import sys
from pathlib import Path
idx_path, answer_path = map(Path, sys.argv[1:])
if not idx_path.exists():
    raise SystemExit(0)
idx = json.loads(idx_path.read_text(encoding='utf-8'))
print('index_entries', len(idx))
answers = [json.loads(x) for x in answer_path.read_text(encoding='utf-8').splitlines() if x.strip()]
docs = {d for row in answers for d in (row.get('document_ids') or [])}
print('answer_doc_ids', len(docs), 'missing_from_uuid_index', len(docs - set(idx)))
print('missing_sample', sorted(docs - set(idx))[:10])
PY
echo 'CORRECTION_OUTPUTS'
ls -la "$RUN" | grep -E 'questions_updated|results|score|answer' || true
