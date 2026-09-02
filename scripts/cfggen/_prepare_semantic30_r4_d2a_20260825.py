"""Prepare Semantic-only D2a: widen the S1 multi-view candidate pool."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "configs/eval_semantic30_r4_s1_lexical_anchor_20260820.yaml"


def main() -> None:
    cfg = deepcopy(yaml.safe_load(SOURCE.read_text(encoding="utf-8")))
    name = "semantic30_r4_d2a_wide_candidates_20260825"
    cfg["pipeline"]["name"] = name
    cfg["pipeline"]["resume"] = False
    cfg["pipeline"]["resume_legacy"] = False
    # This is the sole functional change from S1.  `candidate_k` is used as
    # the top-k returned by every multi-view retrieval leg and as the RRF
    # candidate budget before the existing reranker reduces it to 30.
    cfg["retrieval"]["reranker"]["candidate_k"] = 180
    target = ROOT / "configs" / f"eval_{name}.yaml"
    target.write_text(
        "# Fixed 30 Semantic questions; D2a candidate-pool width only.\n"
        "# Inherits S1 exactly; reranker candidate_k/RRF pool: 120 -> 180.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
