#!/usr/bin/env bash
set -euo pipefail
RUN=/opt/enterprise-rag-bench/app/outputs/pageindex_balanced50_bge_rerank_question_only_llm_route_20260814
/root/anaconda3/bin/python - "$RUN/route_trace.jsonl" <<'PY'
import json, sys
from collections import Counter
path = sys.argv[1]
rows = [json.loads(line) for line in open(path, encoding='utf-8') if line.strip()]
print('TRACE_ROWS', len(rows))
print('SOURCES', Counter(row.get('question_type_source') for row in rows))
print('INFERRED', Counter(row.get('inferred_question_type') for row in rows))
for row in rows[:10]:
    print(row.get('question_id'), row.get('inferred_question_type'), row.get('plan', {}).get('mode'), row.get('route_action'))
PY
