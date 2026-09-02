"""Prepare Semantic-only D1: document-first selection and local evidence search."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "configs/eval_semantic30_r4_s1_lexical_anchor_20260820.yaml"


def main() -> None:
    cfg = deepcopy(yaml.safe_load(SOURCE.read_text(encoding="utf-8")))
    name = "semantic30_r4_d1_document_first_20260821"
    cfg["pipeline"]["name"] = name
    cfg["pipeline"]["resume"] = False
    cfg["pipeline"]["resume_legacy"] = False
    cfg["retrieval"]["semantic_document_first"] = {
        "enabled": True,
        "types": ["semantic"],
        "max_candidate_docs": 12,
        "card_chunks_per_doc": 3,
        "card_chars_per_chunk": 700,
        "candidate_rrf_k": 60,
        "document_rerank_top_n": 3,
        "analysis_enabled": True,
        "analysis_top_n": 3,
        "analysis_min_confidence": 55,
        "local_seed_chunks": 5,
        "local_neighbor_chunks": 1,
        "local_max_expanded_chunks": 10,
        "local_rerank_top_n": 20,
    }
    target = ROOT / "configs" / f"eval_{name}.yaml"
    target.write_text(
        "# Fixed 30 Semantic questions; D1 document-first selection.\n"
        "# Inherits S1 and only replaces final Semantic evidence selection.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
