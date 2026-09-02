"""Create a strict PageIndex ON/OFF A/B over the fixed stratified 50 questions."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "configs/eval_pageindex_balanced50_bge_semantic_consensus_rescue_20260818.yaml"
RUN_PREFIX = "pageindex_ab50_semantic_consensus_20260820_r3"


def write_config(enabled: bool) -> None:
    cfg = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    cfg = deepcopy(cfg)
    variant = "on" if enabled else "off"
    run_name = f"{RUN_PREFIX}_{variant}"
    cfg["pageindex"]["enabled"] = enabled
    # Reuse the existing content-addressed cache for a production-like warm run.
    # The OFF branch never reads this directory.
    cfg["pageindex"]["cache_dir"] = (
        ".pageindex_cache/pageindex_balanced50_bge_semantic_consensus_rescue_20260818"
        if enabled
        else f".pageindex_cache/{run_name}"
    )
    cfg["pipeline"]["name"] = run_name
    cfg["pipeline"]["resume"] = False
    cfg["pipeline"]["resume_legacy"] = False
    cfg["pipeline"]["checkpoint_interval"] = 1
    cfg["pipeline"]["question_parallelism"] = 1
    target = ROOT / "configs" / f"eval_{run_name}.yaml"
    target.write_text(
        "# Strict PageIndex ON/OFF A/B over the fixed stratified 50 questions.\n"
        "# All fields except pipeline identity, cache path, and pageindex.enabled match.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(target)


def main() -> None:
    write_config(True)
    write_config(False)


if __name__ == "__main__":
    main()
