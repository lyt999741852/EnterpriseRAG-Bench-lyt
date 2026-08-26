"""Create the isolated A3.5 generation-conflict-guard smoke config."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "configs" / "eval_pageindex_ab50_semantic_conflict_contract_r2_20260826.yaml"
TARGET = ROOT / "configs" / "eval_pageindex_semantic_conflict_guard_smoke6_20260826.yaml"

SMOKE_QUESTION_IDS = [
    "qst_0236",  # completeness/answer scope control
    "qst_0272",  # recovered selector target
    "qst_0298",  # AB50 correctness regression target
    "qst_0432",  # extra-document diagnostic control
    "qst_0184",  # refusal control
    "qst_0211",  # successful answer control
]


def main() -> None:
    cfg = deepcopy(yaml.safe_load(SOURCE.read_text(encoding="utf-8")))
    cfg["pipeline"]["name"] = "pageindex_semantic_conflict_guard_smoke6_20260826"
    cfg["pipeline"]["question_ids"] = SMOKE_QUESTION_IDS
    cfg["pipeline"]["resume"] = False
    cfg["pipeline"]["resume_legacy"] = False
    # The reranker is shared and has reset connections under concurrent smoke
    # requests; use one worker for a clean, reproducible six-question probe.
    cfg["pipeline"]["question_parallelism"] = 1
    cfg["pageindex"]["cache_dir"] = (
        ".pageindex_cache/pageindex_balanced50_bge_semantic_consensus_rescue_20260818"
    )
    cfg["evaluation"] = {"enabled": False}
    TARGET.write_text(
        "# A3.5 generation-stage conflict guard smoke: six fixed AB50 regression/control questions.\n"
        "# Retrieval and PageIndex settings inherit the frozen r2 AB50 configuration.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(TARGET)


if __name__ == "__main__":
    main()
