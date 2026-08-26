"""Create the PageIndex ON AB50 re-test config for A3.5."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "configs" / "eval_pageindex_ab50_semantic_conflict_contract_r2_20260826.yaml"
TARGET = ROOT / "configs" / "eval_pageindex_ab50_semantic_conflict_guard_r3_20260826.yaml"


def main() -> None:
    cfg = deepcopy(yaml.safe_load(SOURCE.read_text(encoding="utf-8")))
    cfg["pipeline"]["name"] = "pageindex_ab50_semantic_conflict_guard_r3_20260826"
    cfg["pipeline"]["question_parallelism"] = 2
    cfg["pipeline"]["resume"] = False
    cfg["pipeline"]["resume_legacy"] = False
    cfg["pageindex"]["cache_dir"] = (
        ".pageindex_cache/pageindex_balanced50_bge_semantic_consensus_rescue_20260818"
    )
    cfg["evaluation"] = {"enabled": False}
    TARGET.write_text(
        "# A3.5 PageIndex ON AB50 re-test; retrieval and selector inherit r2,\n"
        "# with the generation-stage conflict guard applied at runtime.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(TARGET)


if __name__ == "__main__":
    main()
