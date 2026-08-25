#!/usr/bin/env bash
# Apply only the B3.1 question-planned multi-document experiment.
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
TARGET="$APP/src/pageindex_router.py"

python - "$TARGET" <<'PY'
import sys
from pathlib import Path

target = Path(sys.argv[1])
text = target.read_text(encoding="utf-8")
if 'def _promote_question_planned_multidoc(' in text:
    print("B3_1_MULTIDOC=already_present")
    raise SystemExit(0)

method_needle = '''        return replace(plan, **values) if values else plan

    @property
'''
method_replacement = '''        return replace(plan, **values) if values else plan

    def _promote_question_planned_multidoc(
        self, plan: EvidencePlan, search_plan: QuestionSearchPlan
    ) -> EvidencePlan:
        """Promote a contradictory single-file plan using question-only facets.

        The opt-in rule consumes only the search plan produced from the question.
        It deliberately preserves every retrieval and selection budget so the
        experiment isolates evidence mode from candidate widening.
        """
        config = self.config.mode_budgets.get("question_planned_multidoc", {})
        if not config or not bool(config.get("enabled", False)):
            return plan
        if plan.mode != "single_multisection":
            return plan
        try:
            minimum_facets = max(2, int(config.get("min_facets", 4)))
        except (TypeError, ValueError):
            minimum_facets = 4
        if len(search_plan.facets) < minimum_facets:
            return plan

        constraints = " ".join(search_plan.hard_constraints).casefold()
        has_scope_marker = bool(re.search(
            r"\\b(environment|deployment|channel|platform|hosted|dedicated)\\b",
            constraints,
        ))
        has_multiple_scopes = bool(re.search(
            r"\\b(and|both|across)\\b|\\+|/",
            constraints,
        ))
        if not (has_scope_marker and has_multiple_scopes):
            return plan

        return replace(
            plan,
            mode="multi_hop",
            estimated_documents=max(
                2, min(len(search_plan.facets), plan.candidate_documents)
            ),
        )

    @property
'''
route_needle = '''        search_plan = self._build_search_plan(question, plan)
        max_hops = min(plan.max_hops, self.config.max_hops)
'''
route_replacement = '''        search_plan = self._build_search_plan(question, plan)
        promoted_plan = self._promote_question_planned_multidoc(plan, search_plan)
        if promoted_plan != plan:
            plan = promoted_plan
            self.last_trace["plan"] = asdict(plan)
            self.last_trace["question_planned_multidoc"] = {
                "enabled": True,
                "facet_count": len(search_plan.facets),
                "hard_constraints": list(search_plan.hard_constraints),
                "budgets_preserved": True,
            }
        max_hops = min(plan.max_hops, self.config.max_hops)
'''
for needle in (method_needle, route_needle):
    if text.count(needle) != 1:
        raise RuntimeError("expected B3.1 router context is absent or ambiguous")
text = text.replace(method_needle, method_replacement, 1)
text = text.replace(route_needle, route_replacement, 1)
target.write_text(text, encoding="utf-8")
print("B3_1_MULTIDOC=applied")
PY
