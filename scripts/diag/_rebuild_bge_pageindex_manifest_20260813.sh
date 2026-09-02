#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
CORPUS="$APP/corpus/all_documents"
CACHE="$APP/.index_cache/full_es_bge_small"
MAP_DIR="$APP/.pageindex_manifests"
MAP="$MAP_DIR/bge_corpus_mapping_20260813.sqlite3"
ARCHIVE="$APP/outputs/archive/bge_cache_interrupted_scan_20260813"
PYTHON=/root/anaconda3/envs/embedding_test/bin/python

if pgrep -af 'eval_bge_semantic12_answer_schema_quota_20260813.yaml' >/dev/null; then
  echo "REFUSED_EXPERIMENT_STILL_RUNNING"
  exit 2
fi

mkdir -p "$MAP_DIR" "$ARCHIVE"
CORPUS="$CORPUS" MAP="$MAP" "$PYTHON" - <<'PY'
import os
import sqlite3
from pathlib import Path

corpus = Path(os.environ['CORPUS'])
target = Path(os.environ['MAP'])
temp = target.with_suffix(target.suffix + '.tmp')
if temp.exists():
    temp.unlink()

db = sqlite3.connect(temp)
try:
    db.execute('PRAGMA synchronous=NORMAL')
    db.execute('PRAGMA journal_mode=DELETE')
    db.execute('''
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    db.execute('''
        CREATE TABLE documents (
            file_path TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            file_size INTEGER,
            mtime_ns INTEGER,
            content_hash TEXT,
            status TEXT NOT NULL,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            error_message TEXT NOT NULL DEFAULT ''
        )
    ''')
    db.execute('CREATE INDEX documents_doc_id_idx ON documents(doc_id)')
    batch = []
    total = 0
    unique_doc_ids = set()
    for source in sorted(path for path in corpus.iterdir() if path.is_dir()):
        for path in source.rglob('*.txt'):
            if not path.is_file():
                continue
            stat = path.stat()
            relative = path.relative_to(corpus).as_posix()
            doc_id = path.stem.split('__')[0]
            unique_doc_ids.add(doc_id)
            batch.append((
                relative, doc_id, source.name, stat.st_size, stat.st_mtime_ns,
                '', 'chunked' if stat.st_size else 'skipped', 0,
                '' if stat.st_size else 'empty document',
            ))
            total += 1
            if len(batch) >= 10000:
                db.executemany('''
                    INSERT INTO documents(
                        file_path, doc_id, source_type, file_size, mtime_ns,
                        content_hash, status, chunk_count, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', batch)
                batch.clear()
    if batch:
        db.executemany('''
            INSERT INTO documents(
                file_path, doc_id, source_type, file_size, mtime_ns,
                content_hash, status, chunk_count, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', batch)
    metadata = {
        'preprocess_complete': '1',
        'preprocess_fingerprint': 'pageindex-path-map-reconstructed-20260813',
        'manifest_purpose': 'pageindex_read_only_path_mapping',
        'file_count': str(total),
        'unique_doc_ids': str(len(unique_doc_ids)),
    }
    db.executemany('INSERT INTO metadata(key, value) VALUES (?, ?)', metadata.items())
    db.commit()
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert db.execute('SELECT COUNT(*) FROM documents').fetchone()[0] == 511961
    assert db.execute('SELECT COUNT(DISTINCT doc_id) FROM documents').fetchone()[0] == 511957
finally:
    db.close()
os.replace(temp, target)
print(f'created={target} files={total} unique_doc_ids={len(unique_doc_ids)}')
PY

# Preserve every interrupted-scan artifact before restoring a complete mapping
# at the legacy location used by older PageIndex configurations.
for name in manifest.sqlite3 manifest.sqlite3-journal chunks.jsonl.partial; do
  if [ -e "$CACHE/$name" ]; then
    mv "$CACHE/$name" "$ARCHIVE/$name"
  fi
done
cp -p "$MAP" "$CACHE/manifest.sqlite3"

echo ARCHIVE
find "$ARCHIVE" -maxdepth 1 -type f -printf '%f %s bytes\n' | sort
echo REPAIRED
"$PYTHON" - <<'PY'
import sqlite3
for path in (
    '/opt/enterprise-rag-bench/app/.pageindex_manifests/bge_corpus_mapping_20260813.sqlite3',
    '/opt/enterprise-rag-bench/app/.index_cache/full_es_bge_small/manifest.sqlite3',
):
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        print(path, db.execute('pragma integrity_check').fetchone()[0],
              db.execute('select count(*) from documents').fetchone()[0],
              db.execute('select count(distinct doc_id) from documents').fetchone()[0])
    finally:
        db.close()
PY
echo MAIN_CHUNKS
wc -l "$CACHE/chunks.jsonl"
echo ES_COUNT
curl -fsS 'http://127.0.0.1:9200/enterprise-rag-bge-small-v1/_count?filter_path=count'
echo
