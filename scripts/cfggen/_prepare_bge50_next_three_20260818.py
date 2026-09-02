"""Prepare the next three fixed-50 BGE experiments.

All variants derive from the established question-only multiview baseline.
Each changes one bounded axis and gets its own pipeline/cache/output name.
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "configs/eval_pageindex_balanced50_bge_rerank_question_only_llm_route_multiview_20260814.yaml"


def write_variant(label: str, mutate) -> Path:
    cfg = yaml.safe_load(BASE.read_text(encoding="utf-8"))
    cfg = copy.deepcopy(cfg)
    run = f"pageindex_balanced50_bge_next_{label}_20260818"
    mutate(cfg)
    cfg["pipeline"]["name"] = run
    cfg["pageindex"]["cache_dir"] = f".pageindex_cache/{run}"
    path = ROOT / "configs" / f"eval_{run}.yaml"
    path.write_text(
        "# Fixed 50-question experiment derived from the established BGE multiview baseline.\n"
        "# Official evaluation mode: --no-correction.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def main() -> None:
    paths = []
    paths.append(write_variant(
        "candidate_pool",
        lambda cfg: (
            cfg["retrieval"].update(candidate_k=480),
            cfg["retrieval"]["reranker"].update(candidate_k=240),
        ),
    ))
    paths.append(write_variant(
        "evidence_budget",
        lambda cfg: (
            cfg["generation"].update(
                max_context_chunks=12,
                evidence_selection_candidate_chunks=32,
                evidence_selection_max_chunks=12,
            ),
        ),
    ))
    paths.append(write_variant(
        "route_neutral_fallback",
        lambda cfg: cfg["pipeline"]["question_router"].update(enabled=False),
    ))
    for path in paths:
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
