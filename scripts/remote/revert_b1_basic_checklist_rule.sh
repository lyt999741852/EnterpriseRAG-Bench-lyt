#!/usr/bin/env bash
# Revert only the exact B1 Basic checklist experiment rule on the remote runner.
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
TARGET="$APP/src/generator.py"

python - "$TARGET" <<'PY'
import sys
from pathlib import Path

target = Path(sys.argv[1])
text = target.read_text(encoding="utf-8")
rule = '''            "basic": (
                "Treat every explicitly requested item, condition, value, action and "
                "outcome as a required evidence-backed checklist. Before finalizing, verify "
                "that the answer covers each requested fact that the admitted evidence supports. "
                "Do not replace a requested concrete fact with a generic summary, and do not "
                "add incidental details that the question did not ask for."
            ),
'''
if rule not in text:
    print("B1_BASIC_RULE=already_absent")
    raise SystemExit(0)
if text.count(rule) != 1:
    raise RuntimeError("B1 Basic rule is ambiguous")
target.write_text(text.replace(rule, "", 1), encoding="utf-8")
print("B1_BASIC_RULE=reverted")
PY
