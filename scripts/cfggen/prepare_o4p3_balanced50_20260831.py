"""Prepare the O4.P3 fixed-parameter balanced 50-question validation."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "configs/eval_pageindex_o4p3_soft_pool_smoke20_20260831.yaml"
NAME = "pageindex_o4p3_balanced50_20260831"
QUESTION_IDS = [
    "qst_0013", "qst_0018", "qst_0022", "qst_0030", "qst_0035",
    "qst_0041", "qst_0050", "qst_0056", "qst_0079", "qst_0082",
    "qst_0093", "qst_0107", "qst_0112", "qst_0116", "qst_0119",
    "qst_0125", "qst_0154", "qst_0169", "qst_0184", "qst_0197",
    "qst_0211", "qst_0231", "qst_0236", "qst_0241", "qst_0251",
    "qst_0271", "qst_0272", "qst_0280", "qst_0291", "qst_0298",
    "qst_0301", "qst_0322", "qst_0324", "qst_0328", "qst_0341",
    "qst_0350", "qst_0356", "qst_0362", "qst_0386", "qst_0390",
    "qst_0406", "qst_0413", "qst_0416", "qst_0432", "qst_0447",
    "qst_0459", "qst_0470", "qst_0480", "qst_0491", "qst_0498",
]


def main() -> None:
    cfg = deepcopy(yaml.safe_load(SOURCE.read_text(encoding="utf-8")))
    cfg["pipeline"]["name"] = NAME
    cfg["pipeline"]["question_ids"] = QUESTION_IDS
    cfg["pageindex"]["cache_dir"] = ".pageindex_cache/o4p3_balanced50_20260831"
    cfg["pipeline"]["resume"] = False
    target = ROOT / "configs" / f"eval_{NAME}.yaml"
    target.write_text(
        "# O4.P3 fixed parameters, balanced 50-question no-correction validation.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
