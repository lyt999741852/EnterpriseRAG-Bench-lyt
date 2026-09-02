"""Prepare a generic multi-facet evidence-quota PageIndex smoke."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "configs/eval_pageindex_ab50_semantic_conflict_guard_r3_20260826.yaml"
QUESTION_IDS = [
    "qst_0197", "qst_0447", "qst_0356", "qst_0362",
    "qst_0211", "qst_0236", "qst_0272", "qst_0291",
]


def main() -> None:
    cfg = deepcopy(yaml.safe_load(SOURCE.read_text(encoding="utf-8")))
    name = "pageindex_facet_quota_smoke8_20260826"
    cfg["retrieval"]["semantic_evidence_quota"] = {
        "enabled": True,
        "types": ["semantic", "project_related", "completeness"],
        "max_queries": 3,
        "per_query_top_n": 10,
        "per_query_quota": 3,
    }
    cfg["pipeline"]["name"] = name
    cfg["pipeline"]["question_ids"] = QUESTION_IDS
    cfg["pipeline"]["question_parallelism"] = 1
    cfg["pipeline"]["resume"] = False
    cfg["pipeline"]["resume_legacy"] = False
    target = ROOT / "configs" / f"eval_{name}.yaml"
    target.write_text(
        "# Generic facet quota smoke; no benchmark document IDs or question locks.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
