#!/usr/bin/env bash
set -euo pipefail
: "${ERAG_APP_DIR:?ERAG_APP_DIR is required}"
PYTHON_BIN="${PYTHON_BIN:-python}"
INDEX="$ERAG_APP_DIR/outputs/s3_repro_full500_20260903/official_correction_dpv4_20260908/bundle/uuid_index.json"
"$PYTHON_BIN" - "$INDEX" <<'PY'
import collections
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    index = json.load(stream)
counts = collections.Counter(path.split("/", 1)[0] for path in index.values())
print("document_count", len(index))
for source, count in counts.most_common():
    print(source, count)
PY
