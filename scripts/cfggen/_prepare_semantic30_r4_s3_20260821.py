"""Prepare Semantic-only S3: lexical anchor document reserve after reranking."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "configs/eval_semantic30_r4_s1_lexical_anchor_20260820.yaml"


def main() -> None:
    cfg = deepcopy(yaml.safe_load(SOURCE.read_text(encoding="utf-8")))
    name = "semantic30_r4_s3_anchor_rescue_20260821"
    cfg["pipeline"]["name"] = name
    cfg["pipeline"]["resume"] = False
    cfg["pipeline"]["resume_legacy"] = False
    cfg["retrieval"]["semantic_anchor_rescue"] = {
        "enabled": True,
        "types": ["semantic"],
        "keyword_top_n": 6,
        "max_anchor_docs": 2,
        "max_chunks_per_doc": 2,
        "min_query_token_hits": 2,
        "insertion_after_chunks": 8,
    }
    target = ROOT / "configs" / f"eval_{name}.yaml"
    target.write_text(
        "# Fixed 30 Semantic questions; S3 lexical-anchor document reserve.\n"
        "# Inherits S1 weights; only Semantic retrieval is changed.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
