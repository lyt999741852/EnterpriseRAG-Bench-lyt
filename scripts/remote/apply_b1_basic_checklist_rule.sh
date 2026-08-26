#!/usr/bin/env bash
# Apply the minimal B1 rule only if the expected generator context is intact.
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
TARGET="$APP/src/generator.py"

python - "$TARGET" <<'PY'
import sys
from pathlib import Path

target = Path(sys.argv[1])
text = target.read_text(encoding="utf-8")
if '"basic": (' in text:
    print("B1_BASIC_RULE=already_present")
    raise SystemExit(0)

needle = '''        rules = {
            "semantic": (
'''
replacement = '''        rules = {
            "basic": (
                "Treat every explicitly requested item, condition, value, action and "
                "outcome as a required evidence-backed checklist. Before finalizing, verify "
                "that the answer covers each requested fact that the admitted evidence supports. "
                "Do not replace a requested concrete fact with a generic summary, and do not "
                "add incidental details that the question did not ask for."
            ),
            "semantic": (
'''
if text.count(needle) != 1:
    raise RuntimeError("expected generator rule context is absent or ambiguous")
target.write_text(text.replace(needle, replacement), encoding="utf-8")
print("B1_BASIC_RULE=applied")
PY
