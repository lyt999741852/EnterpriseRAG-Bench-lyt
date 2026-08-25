#!/usr/bin/env bash
# Revert only the exact B3.1 experiment from the remote router.
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
TARGET="$APP/src/pageindex_router.py"

python - "$TARGET" <<'PY'
import sys
from pathlib import Path

target = Path(sys.argv[1])
text = target.read_text(encoding="utf-8")
method_start = text.find("    def _promote_question_planned_multidoc(\n")
method_end = text.find("    @property\n", method_start)
if method_start < 0:
    print("B3_1_MULTIDOC=already_absent")
    raise SystemExit(0)
if method_end < 0:
    raise RuntimeError("B3.1 method end marker is absent")
text = text[:method_start] + text[method_end:]

route_block = '''        promoted_plan = self._promote_question_planned_multidoc(plan, search_plan)
        if promoted_plan != plan:
            plan = promoted_plan
            self.last_trace["plan"] = asdict(plan)
            self.last_trace["question_planned_multidoc"] = {
                "enabled": True,
                "facet_count": len(search_plan.facets),
                "hard_constraints": list(search_plan.hard_constraints),
                "budgets_preserved": True,
            }
'''
if text.count(route_block) != 1:
    raise RuntimeError("B3.1 route block is absent or ambiguous")
text = text.replace(route_block, "", 1)
target.write_text(text, encoding="utf-8")
print("B3_1_MULTIDOC=reverted")
PY
