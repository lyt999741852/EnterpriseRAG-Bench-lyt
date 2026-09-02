"""Prepare the R11.C conditional structured-reserve smoke configuration."""

from copy import deepcopy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "configs/eval_pageindex_r11b_structured_query_smoke_r2_20260827.yaml"
QUESTION_IDS = [
    "qst_0116", "qst_0184", "qst_0231", "qst_0251", "qst_0298",
    "qst_0093", "qst_0211", "qst_0272", "qst_0356",
]


def main() -> None:
    cfg = deepcopy(yaml.safe_load(SOURCE.read_text(encoding="utf-8")))
    name = "pageindex_r11c_conditional_structured_reserve_smoke_20260827"
    cfg["retrieval"]["structured_query"] = {
        "enabled": True,
        "types": ["semantic", "basic", "constrained", "unknown"],
        "agreement_top_docs": 8,
        "min_shared_docs": 1,
        "candidate_top_n": 40,
        "keyword_weight": 0.22,
        "dense_weight": 0.22,
        "max_chunks_per_doc": 2,
        "original_reserve_chunks": 12,
    }
    cfg["pipeline"]["name"] = name
    cfg["pipeline"]["question_ids"] = QUESTION_IDS
    cfg["pipeline"]["question_parallelism"] = 2
    cfg["pipeline"]["resume"] = False
    cfg["pipeline"]["resume_legacy"] = False
    target = ROOT / "configs" / f"eval_{name}.yaml"
    target.write_text(
        "# R11.C: conditional structured reserve on original keyword/dense disagreement.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
