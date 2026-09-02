#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
CONFIG="$APP/configs/eval_pageindex_stratified100_bge_rerank_cpu_20260813.yaml"
MANIFEST="$APP/.pageindex_manifests/bge_corpus_mapping_20260813.sqlite3"
PYTHON=/root/anaconda3/envs/embedding_test/bin/python
cd "$APP"

test -f "$CONFIG"
test -f "$MANIFEST"
"$PYTHON" -m py_compile src/pipeline.py
"$PYTHON" - <<'PY'
import json
import sqlite3
import yaml
from collections import Counter

with open('configs/eval_pageindex_stratified100_bge_rerank_cpu_20260813.yaml', encoding='utf-8') as handle:
    cfg = yaml.safe_load(handle)
questions = {}
with open('questions.jsonl', encoding='utf-8') as handle:
    for line in handle:
        if line.strip():
            item = json.loads(line)
            questions[item['question_id']] = item
ids = cfg['pipeline']['question_ids']
expected = {
    'basic': 35, 'semantic': 25, 'intra_document_reasoning': 8,
    'project_related': 8, 'constrained': 6, 'completeness': 4,
    'conflicting_info': 4, 'info_not_found': 4, 'miscellaneous': 4,
    'high_level': 2,
}
assert len(ids) == 100 and len(set(ids)) == 100
assert Counter(questions[qid]['question_type'] for qid in ids) == Counter(expected)
assert cfg['pipeline']['read_existing_index'] is True
assert cfg['pipeline']['overwrite_index'] is False
assert 'answer_intent_quota' not in cfg['retrieval']
db = sqlite3.connect('file:.pageindex_manifests/bge_corpus_mapping_20260813.sqlite3?mode=ro', uri=True)
try:
    assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
    assert db.execute('select count(*) from documents').fetchone()[0] == 511961
finally:
    db.close()
print('remote_config=OK')
print('questions=100')
print('type_counts=' + json.dumps(expected, sort_keys=True))
print('manifest=OK:511961')
PY

echo -n "cluster_health="
curl -fsS 'http://127.0.0.1:9200/_cluster/health?filter_path=status,timed_out,number_of_nodes,active_primary_shards,unassigned_shards'
echo
echo -n "alias="
curl -fsS 'http://127.0.0.1:9200/_alias/enterprise-rag-bge-small?filter_path=*.aliases'
echo
echo -n "index_count="
curl -fsS 'http://127.0.0.1:9200/enterprise-rag-bge-small-v1/_count?filter_path=count'
echo
echo MATCHING_PROCESSES
pgrep -af 'eval_pageindex_stratified100_bge_rerank_cpu_20260813.yaml' || true
