"""Prepare O4.P3.4 deterministic conflict-constraint smoke."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "configs/eval_pageindex_o4p3_balanced50_20260831.yaml"
NAME = "pageindex_o4p34_deterministic_conflict_smoke4_r1_20260831"
QUESTION_IDS = ["qst_0413", "qst_0416", "qst_0322", "qst_0386"]


def main() -> None:
    cfg = deepcopy(yaml.safe_load(SOURCE.read_text(encoding="utf-8")))
    cfg["pipeline"]["name"] = NAME
    cfg["pipeline"]["question_ids"] = QUESTION_IDS
    cfg["pipeline"]["question_parallelism"] = 2
    cfg["pipeline"]["resume"] = False
    cfg["pageindex"]["cache_dir"] = ".pageindex_cache/o4p34_deterministic_conflict_smoke4_r1_20260831"
    target = ROOT / "configs" / f"eval_{NAME}.yaml"
    target.write_text(
        "# O4.P3.4: deterministic duration constraint for conflicting_info only.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
