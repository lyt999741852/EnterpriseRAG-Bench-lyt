"""Prepare Semantic-only S2: bounded same-document neighbor expansion."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "configs/eval_semantic30_r4_s1_lexical_anchor_20260820.yaml"


def main() -> None:
    cfg = deepcopy(yaml.safe_load(SOURCE.read_text(encoding="utf-8")))
    name = "semantic30_r4_s2_parent_window_20260820"
    cfg["pipeline"]["name"] = name
    cfg["pipeline"]["resume"] = False
    cfg["pipeline"]["resume_legacy"] = False
    cfg["retrieval"]["parent_expansion"] = {
        "enabled": True,
        "types": ["semantic"],
        "neighbor_chunks": 1,
        "max_seed_results": 3,
        "max_expanded_chunks": 8,
    }
    target = ROOT / "configs" / f"eval_{name}.yaml"
    target.write_text(
        "# Fixed 30 Semantic questions; S2 bounded same-document neighbor window.\n"
        "# Expansion is restricted to Semantic and does not affect other routes.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
