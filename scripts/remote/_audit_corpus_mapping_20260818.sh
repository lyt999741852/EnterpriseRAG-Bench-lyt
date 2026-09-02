#!/usr/bin/env bash
set -u
APP=/opt/enterprise-rag-bench/app
echo 'CORPUS_COUNTS'
find "$APP/corpus/all_documents" -type f -name '*.txt' | wc -l
find "$APP/corpus/all_documents" -type f | wc -l
echo 'NON_STANDARD_NAMES'
find "$APP/corpus/all_documents" -type f -name '*.txt' -printf '%f\n' | grep -v '^dsid_[0-9a-f]\{32\}__' | head -30 || true
echo 'UUID_MAPPING_GAPS'
python - "$APP/EnterpriseRAG-Bench/generated_data/uuid_index.json" "$APP/corpus/all_documents" <<'PY'
import json
import sys
from pathlib import Path
idx_path, corpus = map(Path, sys.argv[1:])
idx = json.loads(idx_path.read_text(encoding='utf-8'))
corpus_ids = set()
for p in corpus.rglob('*.txt'):
    name = p.name
    if name.startswith('dsid_'):
        corpus_ids.add(name.split('__', 1)[0])
print('uuid_index_entries', len(idx))
print('corpus_unique_dsid_prefixes', len(corpus_ids))
print('corpus_not_indexed', len(corpus_ids - set(idx)), sorted(corpus_ids - set(idx))[:20])
print('index_not_in_corpus', len(set(idx) - corpus_ids), sorted(set(idx) - corpus_ids)[:20])
PY
