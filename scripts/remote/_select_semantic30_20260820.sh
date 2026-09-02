#!/usr/bin/env bash
set -u
APP=/opt/enterprise-rag-bench/app
python - "$APP/questions.jsonl" <<'PY'
import json,sys
from collections import Counter,defaultdict
rows=[json.loads(line) for line in open(sys.argv[1],encoding='utf-8') if line.strip()]
sem=[r for r in rows if r.get('question_type')=='semantic']
print('COUNT',len(sem))
print('SOURCE_COUNTS',dict(Counter(tuple(r.get('source_types') or []) for r in sem)))
print('SAMPLE_EVERY4')
selected=sem[::4][:30]
for r in selected: print(r['question_id'],r.get('source_types'),r['question'])
print('KNOWN_ANCHORS')
for qid in ['qst_0180','qst_0184','qst_0189','qst_0177','qst_0182']:
  r=next((x for x in sem if x['question_id']==qid),None)
  if r: print(r['question_id'],r.get('source_types'),r['question'])
PY
