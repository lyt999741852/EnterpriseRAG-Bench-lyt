"""Create matched 50/100/500 no-correction experiment configurations."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SPECS = [
    (
        "configs/eval_pageindex_balanced50_bge_rerank_question_only_llm_route_multiview_20260814.yaml",
        "pageindex_balanced50_bge_semantic_consensus_rescue_20260818",
    ),
    (
        "configs/eval_pageindex_stratified100_bge_rerank_question_only_llm_route_multiview_p0_20260814.yaml",
        "pageindex_stratified100_bge_semantic_consensus_rescue_20260818",
    ),
    (
        "configs/eval_pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817.yaml",
        "pageindex_full500_bge_semantic_consensus_rescue_20260818",
    ),
]

RESCUE = {
    "enabled": True,
    # One independent rewrite and one independent answer-intent view must agree.
    "rewrite_queries": 1,
    "intent_queries": 1,
    "per_view_top_n": 8,
    "consensus_top_docs": 2,
    # Never displace an already strong primary-route document.
    "base_anchor_docs": 8,
    "max_rescue_docs": 1,
    "insertion_after_chunks": 8,
}


def main() -> None:
    for source_rel, run_name in SPECS:
        source = ROOT / source_rel
        cfg = yaml.safe_load(source.read_text(encoding="utf-8"))
        cfg = deepcopy(cfg)
        cfg["retrieval"]["semantic_rescue"] = deepcopy(RESCUE)
        cfg["pageindex"]["cache_dir"] = f".pageindex_cache/{run_name}"
        cfg["pipeline"]["name"] = run_name
        cfg["pipeline"]["resume"] = False
        cfg["pipeline"]["resume_legacy"] = False
        cfg["pipeline"]["checkpoint_interval"] = 1
        cfg["pipeline"]["question_parallelism"] = 1
        target = ROOT / "configs" / f"eval_{run_name}.yaml"
        target.write_text(
            "# Matched no-correction semantic consensus-rescue evaluation.\n"
            "# The original hybrid + rerank route is preserved; a single extra\n"
            "# document is admitted only when rewrite and answer-intent agree.\n"
            + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        print(target)


if __name__ == "__main__":
    main()
