"""Prepare the isolated low-weight lexical-anchor-pair smoke."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "configs/eval_pageindex_ab50_semantic_conflict_guard_r3_20260826.yaml"
QUESTION_IDS = [
    "qst_0116", "qst_0184", "qst_0231", "qst_0251",
    "qst_0093", "qst_0211", "qst_0272", "qst_0356",
]


def main() -> None:
    cfg = deepcopy(yaml.safe_load(SOURCE.read_text(encoding="utf-8")))
    name = "pageindex_lexical_anchor_smoke8_20260827"
    cfg["retrieval"]["lexical_anchor_variants"] = {
        "enabled": True,
        "types": ["semantic"],
        "token_limit": 8,
        "max_pair_queries": 20,
        "weight": 0.2,
        "max_chunks_per_doc": 2,
    }
    cfg["generation"]["max_chunks_per_doc"] = 2
    cfg["pipeline"]["name"] = name
    cfg["pipeline"]["question_ids"] = QUESTION_IDS
    cfg["pipeline"]["question_parallelism"] = 1
    cfg["pipeline"]["resume"] = False
    cfg["pipeline"]["resume_legacy"] = False
    target = ROOT / "configs" / f"eval_{name}.yaml"
    target.write_text(
        "# Isolated smoke: low-weight question-derived lexical entity pairs.\n"
        "# No target-document lock; max two chunks per document.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
