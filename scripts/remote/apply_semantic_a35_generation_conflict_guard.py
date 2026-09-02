"""Apply or roll back the A3.5 generation-stage conflict guard remotely.

The selector contract keeps source-priority-resolved disagreements out of the
blocking ``conflicts`` field.  This second, isolated prompt change prevents the
fact verifier/final audit from turning a directly reported value into an
unnecessary abstention when other passages describe a different scope.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


TARGET = Path("src/generator.py")
BACKUP = Path("src/generator.py.a35_generation_guard.bak")

FACT_ANCHOR = "- If multiple passages disagree on a number, date, version or policy status and the applicable\n"
FINAL_ANCHOR = "- When sources differ, prefer a later operational ticket, applied configuration or audit record\n"

FACT_GUARD = """- When one admitted passage directly answers the requested facet under the question's
  scope, preserve that reported value as the answer. Do not turn it into an abstention merely
  because another passage describes a different deployment scope or a broader timeline.
- For questions asking what was told, quoted, proposed or reported, retain the directly reported
  value and label its scope briefly when needed; do not substitute an unrelated alternative.
"""

FINAL_GUARD = """- If an admitted source directly answers the requested facet, lead with that value. A different
  scope or broader timeline in another source must not negate the directly reported value; only
  mention it as a short qualifier when it is necessary to avoid ambiguity.
- For what was told, quoted, proposed or reported questions, preserve the scoped reported value
  instead of replacing it with an uncertainty statement caused by unrelated alternatives.
"""


def apply() -> None:
    if BACKUP.exists():
        raise SystemExit(f"backup already exists: {BACKUP}")
    text = TARGET.read_text(encoding="utf-8")
    if text.count(FACT_ANCHOR) != 1 or text.count(FINAL_ANCHOR) != 1:
        raise SystemExit("generation prompt anchors not found uniquely")
    shutil.copy2(TARGET, BACKUP)
    text = text.replace(FACT_ANCHOR, FACT_GUARD + FACT_ANCHOR, 1)
    text = text.replace(FINAL_ANCHOR, FINAL_GUARD + FINAL_ANCHOR, 1)
    TARGET.write_text(text, encoding="utf-8")
    print("A3.5_GENERATION_CONFLICT_GUARD_APPLIED")


def rollback() -> None:
    if not BACKUP.exists():
        raise SystemExit(f"backup missing: {BACKUP}")
    shutil.copy2(BACKUP, TARGET)
    BACKUP.unlink()
    print("A3.5_GENERATION_CONFLICT_GUARD_ROLLED_BACK")


parser = argparse.ArgumentParser()
parser.add_argument("action", choices=("apply", "rollback"))
args = parser.parse_args()
if args.action == "apply":
    apply()
else:
    rollback()
