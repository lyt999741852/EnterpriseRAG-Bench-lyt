#!/usr/bin/env bash
set -u
APP=/opt/enterprise-rag-bench/app
python - "$APP/EnterpriseRAG-Bench/generated_data/uuid_index.json" "$APP/corpus/all_documents" <<'PY'
import json
import sys
from pathlib import Path
idx_path, corpus = map(Path, sys.argv[1:])
idx = json.loads(idx_path.read_text(encoding='utf-8'))
corpus_ids = set()
for p in corpus.rglob('*.txt'):
    if p.name.startswith('dsid_'):
        corpus_ids.add(p.name.split('__', 1)[0])
for key in sorted(set(idx) - corpus_ids):
    print('INDEX_ONLY', key, idx[key])
dups = {}
for p in corpus.rglob('*.txt'):
    if p.name.startswith('dsid_'):
        key = p.name.split('__', 1)[0]
        dups.setdefault(key, []).append(str(p))
print('DUPLICATE_PREFIXES')
for key, paths in sorted(dups.items()):
    if len(paths) > 1:
        print(key, len(paths), paths[:5])
PY
