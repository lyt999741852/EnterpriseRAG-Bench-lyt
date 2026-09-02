#!/usr/bin/env bash
set -euo pipefail
cache=/opt/enterprise-rag-bench/app/.index_cache/full_es_bge_small
manifest="$cache/manifest.sqlite3"

echo FILES
find "$cache" -maxdepth 1 -type f -printf '%f %s %TY-%Tm-%TdT%TH:%TM:%TS\n' | sort
echo MANIFEST
/root/anaconda3/envs/embedding_test/bin/python - <<'PY'
import json
import sqlite3
from pathlib import Path

path = Path('/opt/enterprise-rag-bench/app/.index_cache/full_es_bge_small/manifest.sqlite3')
db = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
try:
    tables = {row[0] for row in db.execute("select name from sqlite_master where type='table'")}
    print('tables=' + ','.join(sorted(tables)))
    if 'metadata' in tables:
        rows = list(db.execute('select key, value from metadata order by key'))
        print('metadata=' + json.dumps(dict(rows), sort_keys=True))
    if 'documents' in tables:
        print('documents=' + str(db.execute('select count(*) from documents').fetchone()[0]))
finally:
    db.close()
PY
echo ES_COUNT
curl -fsS 'http://127.0.0.1:9200/enterprise-rag-bge-small-v1/_count?filter_path=count'
echo
