#!/usr/bin/env bash
set -u
APP=/opt/enterprise-rag-bench/app
python - "$APP/questions.jsonl" "$APP/outputs/pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817/answers.jsonl" <<'PY'
import json
import sys
from collections import Counter, defaultdict

qpath, apath = sys.argv[1:]
questions = {x['question_id']: x for x in (json.loads(line) for line in open(qpath, encoding='utf-8') if line.strip())}
answers = [json.loads(line) for line in open(apath, encoding='utf-8') if line.strip()]

stats = Counter()
by_type = defaultdict(Counter)
extra_counts = Counter()
missing_counts = Counter()
examples = []
for row in answers:
    qid = row['question_id']
    q = questions[qid]
    gold = set(q.get('expected_doc_ids') or [])
    got = set(row.get('document_ids') or [])
    extra = got - gold
    missing = gold - got
    kind = q.get('question_type')
    if not gold:
        stats['gold_empty'] += 1
    if not got:
        stats['answer_empty'] += 1
    if gold == got:
        stats['exact_set'] += 1
    else:
        stats['set_mismatch'] += 1
    if extra:
        stats['has_extra'] += 1
        extra_counts[len(extra)] += 1
    if missing:
        stats['has_missing'] += 1
        missing_counts[len(missing)] += 1
    if extra or missing:
        by_type[kind]['mismatch'] += 1
        by_type[kind]['extra'] += bool(extra)
        by_type[kind]['missing'] += bool(missing)
        if len(examples) < 12:
            examples.append((qid, kind, sorted(gold), sorted(got), sorted(extra), sorted(missing)))

print('TOTALS', dict(stats))
print('EXTRA_COUNT_DISTRIBUTION', dict(sorted(extra_counts.items())))
print('MISSING_COUNT_DISTRIBUTION', dict(sorted(missing_counts.items())))
print('BY_TYPE')
for kind in sorted(by_type):
    print(kind, dict(by_type[kind]))
print('EXAMPLES')
for item in examples:
    print(item)
PY
