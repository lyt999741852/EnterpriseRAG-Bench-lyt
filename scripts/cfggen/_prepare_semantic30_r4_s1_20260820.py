"""Prepare Semantic-only S1: route-specific lexical-anchor fusion weights."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "configs/eval_semantic30_r4_baseline_off_20260820.yaml"


def main() -> None:
    cfg = deepcopy(yaml.safe_load(SOURCE.read_text(encoding="utf-8")))
    name = "semantic30_r4_s1_lexical_anchor_20260820"
    cfg["pipeline"]["name"] = name
    cfg["pipeline"]["resume"] = False
    cfg["pipeline"]["resume_legacy"] = False
    cfg["retrieval"]["multi_view"]["route_weights"] = {
        "semantic": {
            "original_keyword": 1.5,
            "original_dense": 1.0,
            "rewritten_dense": 0.8,
            "answer_intent_dense": 0.25,
        }
    }
    target = ROOT / "configs" / f"eval_{name}.yaml"
    target.write_text(
        "# Fixed 30 Semantic questions; S1 route-specific lexical-anchor weights.\n"
        "# Global weights remain unchanged for all non-Semantic routes.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
