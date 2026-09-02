#!/usr/bin/env bash
set -u
APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817"
echo 'HASHES'
sha256sum "$APP/questions.jsonl" "$RUN/answers.jsonl" "$RUN/results.json" "$RUN/run_meta.json" 2>/dev/null || true
echo 'ANSWER_SCHEMA'
python - "$APP/questions.jsonl" "$RUN/answers.jsonl" <<'PY'
import json
import sys
from collections import Counter
qpath, apath = sys.argv[1:]
questions = [json.loads(x) for x in open(qpath, encoding='utf-8') if x.strip()]
answers = [json.loads(x) for x in open(apath, encoding='utf-8') if x.strip()]
qids = [x.get('question_id') for x in questions]
aqids = [x.get('question_id') for x in answers]
print('questions', len(questions), 'unique', len(set(qids)))
print('answers', len(answers), 'unique', len(set(aqids)))
print('missing_qids', sorted(set(qids)-set(aqids)))
print('extra_qids', sorted(set(aqids)-set(qids)))
print('duplicate_answer_ids', [k for k,v in Counter(aqids).items() if v > 1])
print('empty_answers', sum(not isinstance(x.get('answer'), str) or not x.get('answer').strip() for x in answers))
print('bad_document_ids', sum(not isinstance(x.get('document_ids'), list) or any(not isinstance(d, str) or not d.startswith('dsid_') for d in x.get('document_ids', [])) for x in answers))
print('max_document_ids', max((len(x.get('document_ids') or []) for x in answers), default=0))
print('question_type_counts', dict(Counter(x.get('question_type') for x in questions)))
PY
echo 'ROUTE_TRACE_SOURCES'
TRACE="$RUN/route_trace.jsonl"
grep -o 'question_type_source[^,}]*' "$TRACE" | sort | uniq -c || true
echo 'LEAKAGE_MARKERS'
for token in benchmark_metadata gold_answer expected_doc_ids answer_facts; do
  count=$(grep -c "$token" "$TRACE" 2>/dev/null || true)
  echo "$token=$count"
done
echo 'INDEX'
curl -sS --max-time 15 http://127.0.0.1:9200/_cat/indices?v 2>/dev/null | grep -E 'enterprise-rag-bge-small|index' | head -20 || true
echo 'RUN_META'
cat "$RUN/run_meta.json" 2>/dev/null || true
