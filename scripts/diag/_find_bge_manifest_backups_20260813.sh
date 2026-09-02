#!/usr/bin/env bash
set -euo pipefail
APP=/opt/enterprise-rag-bench/app
echo CANDIDATES
find "$APP" -type f \( -name 'manifest.sqlite3' -o -name 'manifest.sqlite3.*' -o -name '*manifest*backup*' -o -name 'chunks.jsonl' -o -name '_meta.json' \) \
  -printf '%p %s %TY-%Tm-%TdT%TH:%TM:%TS\n' | sort
echo CACHE_DIRS
find "$APP/.index_cache" -maxdepth 2 -type d -printf '%p\n' | sort
echo PROCESSES
pgrep -af 'src.pipeline|src.build_es_index' || true
