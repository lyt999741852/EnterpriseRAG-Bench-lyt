"""Create the isolated B3.1 question-planned multi-document smoke config."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "configs" / "eval_pageindex_ab50_semantic_consensus_20260820_r3_on.yaml"
TARGET = ROOT / "configs" / "eval_b3_1_multidoc_smoke10_20260825.yaml"

SMOKE_QUESTION_IDS = [
    "qst_0447", "qst_0432",
    "qst_0341", "qst_0350", "qst_0356", "qst_0362",
    "qst_0018", "qst_0125", "qst_0491", "qst_0498",
]


def main() -> None:
    cfg = deepcopy(yaml.safe_load(SOURCE.read_text(encoding="utf-8")))
    name = "b3_1_multidoc_smoke10_20260825"
    cfg["pipeline"]["name"] = name
    cfg["pipeline"]["question_ids"] = SMOKE_QUESTION_IDS
    cfg["pipeline"]["resume"] = False
    cfg["pipeline"]["resume_legacy"] = False
    cfg["pipeline"]["question_parallelism"] = 1
    cfg["pageindex"]["cache_dir"] = ".pageindex_cache/b3_1_multidoc_smoke10_20260825"
    mode_budgets = cfg["pageindex"].setdefault("mode_budgets", {})
    mode_budgets["question_planned_multidoc"] = {
        "enabled": 1,
        "min_facets": 4,
    }
    TARGET.write_text(
        "# B3.1 question-planned multi-document smoke: fixed 10 questions.\n"
        "# No retrieval, reranker, PageIndex, or generation budget is widened.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(TARGET)


if __name__ == "__main__":
    main()
