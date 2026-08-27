"""Prepare the R9 integrated retrieval/routing regression over the AB50 set."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "configs/eval_pageindex_ab50_semantic_conflict_guard_r3_20260826.yaml"


def main() -> None:
    cfg = deepcopy(yaml.safe_load(SOURCE.read_text(encoding="utf-8")))
    name = "pageindex_r9_integrated_retrieval_smoke50_20260827"
    retrieval = cfg["retrieval"]

    # Unknown question-only routes receive the same semantic retrieval budget
    # instead of falling back to the basic ES-only route.
    semantic_views = list(retrieval["multi_view"]["routes"]["semantic"])
    retrieval["multi_view"]["routes"]["unknown"] = semantic_views
    for section in (retrieval["query_rewrite"], retrieval["answer_intent"]):
        section["types"] = list(dict.fromkeys([*section.get("types", []), "unknown"]))

    # Reserve a small number of independently reranked facet results while
    # retaining the primary route ranking.
    retrieval["semantic_evidence_quota"] = {
        "enabled": True,
        "types": ["semantic", "unknown", "project_related", "completeness"],
        "max_queries": 3,
        "per_query_top_n": 8,
        "per_query_quota": 2,
    }
    retrieval["r9_global_document_cap"] = {
        "enabled": True,
        "max_chunks_per_doc": 2,
        "max_total_chunks": 30,
    }

    cfg["pipeline"]["name"] = name
    cfg["pipeline"]["question_parallelism"] = 2
    cfg["pipeline"]["resume"] = False
    cfg["pipeline"]["resume_legacy"] = False
    target = ROOT / "configs" / f"eval_{name}.yaml"
    target.write_text(
        "# R9 integrated retrieval regression: unknown routing, facet quota, global doc cap.\n"
        "# No target-document lock; question-only inputs only.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
