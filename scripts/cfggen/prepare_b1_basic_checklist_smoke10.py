"""Create the isolated B1 Basic fact-checklist smoke configuration."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "configs" / "eval_pageindex_ab50_semantic_consensus_20260820_r3_on.yaml"
TARGET = ROOT / "configs" / "eval_b1_basic_checklist_smoke10_20260825.yaml"

# Three Basic coverage gaps, three Basic controls, and four non-Basic regression
# controls. These IDs select an offline evaluation subset only; routing remains
# question-only and inferred by the production router.
SMOKE_QUESTION_IDS = [
    "qst_0013", "qst_0079", "qst_0119",
    "qst_0018", "qst_0030", "qst_0125",
    "qst_0184", "qst_0341", "qst_0491", "qst_0498",
]


def main() -> None:
    cfg = deepcopy(yaml.safe_load(SOURCE.read_text(encoding="utf-8")))
    name = "b1_basic_checklist_smoke10_20260825"
    cfg["pipeline"]["name"] = name
    cfg["pipeline"]["question_ids"] = SMOKE_QUESTION_IDS
    cfg["pipeline"]["resume"] = False
    cfg["pipeline"]["resume_legacy"] = False
    cfg["pipeline"]["question_parallelism"] = 1
    cfg["pageindex"]["cache_dir"] = ".pageindex_cache/b1_basic_checklist_smoke10_20260825"
    TARGET.write_text(
        "# B1 Basic checklist smoke: fixed 10 questions, PageIndex ON.\n"
        "# Retrieval, PageIndex, and evidence budgets inherit AB50 exactly.\n"
        "# The only behavioral change is the Basic route's answer checklist rule.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(TARGET)


if __name__ == "__main__":
    main()
