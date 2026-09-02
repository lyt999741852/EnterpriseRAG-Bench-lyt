"""Prepare the R10 system-level retrieval smoke over raw-miss and controls."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "configs/eval_pageindex_ab50_semantic_conflict_guard_r3_20260826.yaml"
QUESTION_IDS = [
    "qst_0116", "qst_0184", "qst_0231", "qst_0251", "qst_0298",
    "qst_0197", "qst_0350", "qst_0356", "qst_0362", "qst_0432",
    "qst_0447", "qst_0272",
]


def main() -> None:
    cfg = deepcopy(yaml.safe_load(SOURCE.read_text(encoding="utf-8")))
    name = "pageindex_r10_scope_softcap_anchor_smoke12_r3_20260827"
    retrieval = cfg["retrieval"]
    allowed_types = ["semantic", "unknown", "project_related", "completeness"]

    # Rescue and facet quota are explicitly scoped; basic controls retain the
    # baseline ES-only behavior.
    retrieval["semantic_rescue"]["types"] = allowed_types
    retrieval["semantic_evidence_quota"] = {
        "enabled": True,
        "types": allowed_types,
        "max_queries": 3,
        "per_query_top_n": 8,
        "per_query_quota": 2,
    }
    retrieval["r10_soft_document_quota"] = {
        "enabled": True,
        "max_chunks_per_doc": 2,
        "preserve_one_per_document": True,
        # A soft quota intentionally has no global hard total cap.
        "max_total_chunks": 0,
    }
    retrieval["lexical_anchor_variants"] = {
        "enabled": True,
        "types": allowed_types,
        "token_limit": 10,
        "max_pair_queries": 16,
        "weight": 0.2,
        "max_chunks_per_doc": 2,
    }

    cfg["pipeline"]["name"] = name
    cfg["pipeline"]["question_ids"] = QUESTION_IDS
    # The reranker endpoint reset one request under parallel=2; use a stable
    # single worker for this retry while preserving independent query views.
    cfg["pipeline"]["question_parallelism"] = 1
    cfg["pipeline"]["resume"] = False
    cfg["pipeline"]["resume_legacy"] = False
    target = ROOT / "configs" / f"eval_{name}.yaml"
    target.write_text(
        "# R10 system smoke: route scope, facet-aware soft quota, lexical anchors.\n"
        "# No target-document lock; basic control route remains isolated.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
