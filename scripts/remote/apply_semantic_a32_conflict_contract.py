"""Apply or roll back the isolated A3.2 selector prompt contract remotely."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


TARGET = Path("src/generator.py")
BACKUP = Path("src/generator.py.a32_conflict_contract.bak")
TEMPLATE_END = """  "conflicts": []
}}
"""
CONTRACT = """\nConflict reporting contract:
- `conflicts` is a blocking field. Put only contradictions that remain unresolved after
  applying explicit final/current/canonical/applicable-source precedence in `conflicts`.
- When an accepted passage is explicitly final, current, canonical, or otherwise applicable
  and competing passages are older, draft, or differently scoped, record those resolved
  discrepancies in `resolved_conflicts`, not in `conflicts`.
- If two contradictory passages have equal authority/status and no explicit precedence resolves
  them, keep the contradiction in `conflicts`, set coverage_complete=false, and do not admit
  either concrete conflicting value as an answer fact.
- Never set coverage_complete=true while blocking `conflicts` is non-empty.
- Return `resolved_conflicts` as a JSON list in addition to the existing fields.
"""
CONTRACTED_TEMPLATE = TEMPLATE_END + CONTRACT


def apply() -> None:
    if BACKUP.exists():
        raise SystemExit(f"backup already exists: {BACKUP}")
    text = TARGET.read_text(encoding="utf-8")
    if TEMPLATE_END not in text:
        raise SystemExit("A3.2 prompt template end not found")
    shutil.copy2(TARGET, BACKUP)
    TARGET.write_text(text.replace(TEMPLATE_END, CONTRACTED_TEMPLATE, 1), encoding="utf-8")
    print("A3.2_CONFLICT_CONTRACT_APPLIED")


def rollback() -> None:
    if not BACKUP.exists():
        raise SystemExit(f"backup missing: {BACKUP}")
    shutil.copy2(BACKUP, TARGET)
    BACKUP.unlink()
    print("A3.2_CONFLICT_CONTRACT_ROLLED_BACK")


parser = argparse.ArgumentParser()
parser.add_argument("action", choices=("apply", "rollback"))
args = parser.parse_args()
if args.action == "apply":
    apply()
else:
    rollback()
