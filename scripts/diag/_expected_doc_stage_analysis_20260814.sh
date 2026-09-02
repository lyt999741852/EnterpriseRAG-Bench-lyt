#!/usr/bin/env bash
set -euo pipefail
APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/pageindex_stratified100_bge_rerank_cpu_20260813"
QUESTIONS="$APP/questions.jsonl"
RUN="$RUN" QUESTIONS="$QUESTIONS" /root/anaconda3/bin/python - <<'PY'
import json, os
from collections import Counter
from pathlib import Path
run=Path(os.environ['RUN'])
questions={}
for line in Path(os.environ['QUESTIONS']).read_text(encoding='utf-8').splitlines():
    if line.strip():
        x=json.loads(line); questions[x['question_id']]=x
results={x['question_id']:x for x in json.loads((run/'results.json').read_text(encoding='utf-8'))['questions']}
traces={}
for line in (run/'route_trace.jsonl').read_text(encoding='utf-8').splitlines():
    if line.strip():
        x=json.loads(line); traces[x['question_id']]=x
answers={}
for line in (run/'answers.jsonl').read_text(encoding='utf-8').splitlines():
    if line.strip():
        x=json.loads(line); answers[x['question_id']]=x
for typ in ('semantic','project_related','completeness'):
    rows=[r for r in results.values() if r['question_type']==typ]
    stages=Counter()
    print('\nTYPE',typ,'n=',len(rows))
    for r in rows:
        qid=r['question_id']; gold=set(questions[qid].get('expected_doc_ids',[])); t=traces[qid]; a=set(answers[qid].get('document_ids',[]))
        candidate={d.get('doc_id') for d in t.get('pageindex_documents',[]) if d.get('doc_id')}
        selected=set(t.get('selected_document_ids',[]))|set(t.get('full_document_expansions',[]))
        stages['candidate_hit' if gold & candidate else 'candidate_miss']+=1
        stages['selected_hit' if gold & selected else 'selected_miss']+=1
        stages['answer_hit' if gold & a else 'answer_miss']+=1
    print('STAGES',dict(stages))
PY
