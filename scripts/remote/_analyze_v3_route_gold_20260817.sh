#!/usr/bin/env bash
set -u
python - <<'PY'
import json
from collections import Counter, defaultdict

app = '/opt/enterprise-rag-bench/app'
questions = {}
with open(f'{app}/questions.jsonl', encoding='utf-8') as f:
    for line in f:
        if line.strip():
            row = json.loads(line)
            questions[row['question_id']] = row.get('question_type', 'unknown')

trace = f'{app}/outputs/pageindex_stratified100_qwen3_v3_p0_r2_candidate_pool_20260817/route_trace.jsonl'
matrix = defaultdict(Counter)
actions = defaultdict(Counter)
for line in open(trace, encoding='utf-8'):
    if not line.strip():
        continue
    row = json.loads(line)
    qid = row.get('question_id')
    gold = questions.get(qid, 'missing')
    inferred = row.get('inferred_question_type', 'none')
    action = row.get('route_action', 'none')
    matrix[gold][inferred] += 1
    actions[gold][action] += 1

print('GOLD_TO_INFERRED')
for gold in sorted(matrix):
    print(gold, dict(sorted(matrix[gold].items())))
print('GOLD_TO_ACTION')
for gold in sorted(actions):
    print(gold, dict(sorted(actions[gold].items())))
PY
