#!/usr/bin/env bash
set -euo pipefail

: "${ERAG_APP_DIR:?ERAG_APP_DIR is required}"
PYTHON_BIN="${PYTHON_BIN:-python}"
OUT="$ERAG_APP_DIR/outputs/s3_repro_full500_20260903/official_correction_qwen_20260908"
echo "files"
ls -lh "$OUT" 2>/dev/null || true
echo "score"
tail -n 15 "$OUT/score.log" 2>/dev/null || true
echo "progress"
"$PYTHON_BIN" - "$OUT/results.json" <<'PY' 2>/dev/null || true
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    print("results_rows=0")
    raise SystemExit
data = json.loads(path.read_text(encoding="utf-8"))
if isinstance(data, list):
    print(f"results_rows={len(data)}")
elif isinstance(data, dict):
    for key in ("results", "question_results", "evaluations"):
        if isinstance(data.get(key), list):
            print(f"results_rows={len(data[key])}")
            break
    else:
        print("results_json_present=true")
PY
echo "processes"
pgrep -af 'metrics_based_eval' || true
