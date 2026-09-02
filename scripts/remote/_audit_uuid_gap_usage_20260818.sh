#!/usr/bin/env bash
set -u
APP=/opt/enterprise-rag-bench/app
python - "$APP/questions.jsonl" "$APP/EnterpriseRAG-Bench/generated_data/uuid_index.json" "$APP/outputs/pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817/answers.jsonl" <<'PY'
import json
import sys
qpath, ipath, apath = sys.argv[1:]
gap = 'dsid_bc8604e62eec448d9a9c1b07eb003975'
questions = [json.loads(x) for x in open(qpath, encoding='utf-8') if x.strip()]
answers = [json.loads(x) for x in open(apath, encoding='utf-8') if x.strip()]
gold = [q['question_id'] for q in questions if gap in (q.get('expected_doc_ids') or [])]
retrieved = [a['question_id'] for a in answers if gap in (a.get('document_ids') or [])]
print('gold_usage', gold)
print('answer_usage', retrieved)
PY
