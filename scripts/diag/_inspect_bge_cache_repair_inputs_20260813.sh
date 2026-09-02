#!/usr/bin/env bash
set -euo pipefail
APP=/opt/enterprise-rag-bench/app
cache="$APP/.index_cache/full_es_bge_small"

echo META
cat "$cache/_meta.json"
echo
echo MANIFEST_COUNTS
/root/anaconda3/envs/embedding_test/bin/python - <<'PY'
import sqlite3
from pathlib import Path

root = Path('/opt/enterprise-rag-bench/app/corpus/all_documents')
by_source = {}
total = 0
for source in sorted(root.iterdir()):
    if not source.is_dir():
        continue
    count = sum(1 for path in source.rglob('*.txt') if path.is_file())
    by_source[source.name] = count
    total += count
print('corpus_total=', total)
print('corpus_by_source=', by_source)

path = Path('/opt/enterprise-rag-bench/app/.index_cache/full_es_bge_small/manifest.sqlite3')
db = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
try:
    print('manifest_total=', db.execute('select count(*) from documents').fetchone()[0])
    print('manifest_by_source=', dict(db.execute('select source_type, count(*) from documents group by source_type order by source_type')))
finally:
    db.close()
PY
echo CHUNK_LINES
wc -l "$cache/chunks.jsonl" "$cache/chunks.jsonl.partial"
