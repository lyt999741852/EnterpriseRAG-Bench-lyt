"""Prepare the isolated R11.B structured-query candidate-union smoke."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "configs/eval_pageindex_ab50_semantic_conflict_guard_r3_20260826.yaml"
QUESTION_IDS = [
    # Five core raw-miss targets from R1/R6.
    "qst_0116", "qst_0184", "qst_0231", "qst_0251", "qst_0298",
    # Controls: a rerank drop, a route/control recovery, and a multi-hop case.
    "qst_0093", "qst_0211", "qst_0272", "qst_0356",
]


def main() -> None:
    cfg = deepcopy(yaml.safe_load(SOURCE.read_text(encoding="utf-8")))
    name = "pageindex_r11b_structured_query_smoke_20260827"
    cfg["retrieval"]["structured_query"] = {
        "enabled": True,
        "types": ["semantic", "unknown"],
        "keyword_weight": 0.22,
        "dense_weight": 0.22,
        "max_chunks_per_doc": 3,
        "original_reserve_chunks": 12,
    }
    cfg["generation"]["max_chunks_per_doc"] = 4
    cfg["pipeline"]["name"] = name
    cfg["pipeline"]["question_ids"] = QUESTION_IDS
    cfg["pipeline"]["question_parallelism"] = 2
    cfg["pipeline"]["resume"] = False
    cfg["pipeline"]["resume_legacy"] = False
    target = ROOT / "configs" / f"eval_{name}.yaml"
    target.write_text(
        "# Isolated R11.B smoke: one answer-free structured semantic query.\n"
        "# Low-weight BM25/dense union with an explicit original-view reserve.\n"
        "# No target-document lock, answer preset, or index write.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
