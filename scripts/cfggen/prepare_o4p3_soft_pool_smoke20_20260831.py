"""Prepare O4.P3 selector-stability smoke configuration."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "configs/eval_pageindex_o4p2_soft_pool_smoke20_20260831.yaml"
NAME = "pageindex_o4p3_soft_pool_smoke20_20260831"


def main() -> None:
    cfg = deepcopy(yaml.safe_load(SOURCE.read_text(encoding="utf-8")))
    cfg["pipeline"]["name"] = NAME
    cfg["pageindex"]["cache_dir"] = ".pageindex_cache/o4p3_soft_pool_smoke20_20260831"
    generation = cfg["generation"]
    generation["evidence_selection_fail_closed"] = False
    generation["evidence_selection_fallback_chunks"] = 4
    generation["evidence_selection_anchor_chunks"] = 2
    target = ROOT / "configs" / f"eval_{NAME}.yaml"
    target.write_text(
        "# O4.P3: selector stability fallback/anchors with soft pool +2.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
