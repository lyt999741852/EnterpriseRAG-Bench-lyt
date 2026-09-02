"""Freeze the current 500-question config and prepare fixed-50 BGE experiments.

This is intentionally a mechanical derivation from the established multiview
50-question configuration.  The experiment files keep the corpus, index,
model, reranker, PageIndex, evidence selection, and question IDs unchanged;
only the multiview weights and run/cache names differ.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from datetime import date
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
FULL500 = ROOT / "configs/eval_pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817.yaml"
BASE50 = ROOT / "configs/eval_pageindex_balanced50_bge_rerank_question_only_llm_route_multiview_20260814.yaml"
SNAPSHOT_DIR = ROOT / "configs/snapshots"
EXPERIMENT_DIR = ROOT / "configs"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_yaml(path: Path, cfg: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Generated from configs/eval_pageindex_balanced50_bge_rerank_question_only_llm_route_multiview_20260814.yaml\n"
        "# Fixed 50-question set; all optimization comparisons use official no-correction scoring.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def make_variant(label: str, weights: dict[str, float]) -> Path:
    cfg = yaml.safe_load(BASE50.read_text(encoding="utf-8"))
    cfg = copy.deepcopy(cfg)
    cfg["retrieval"]["multi_view"]["weights"].update(weights)
    run_name = f"pageindex_balanced50_bge_keyword_{label}_20260818"
    cfg["pipeline"]["name"] = run_name
    cfg["pageindex"]["cache_dir"] = f".pageindex_cache/{run_name}"
    path = EXPERIMENT_DIR / f"eval_{run_name}.yaml"
    write_yaml(path, cfg)
    return path


def main() -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_config = SNAPSHOT_DIR / FULL500.name
    shutil.copy2(FULL500, snapshot_config)

    variants = {
        "lexical_a": {
            "original_keyword": 1.6,
            "original_dense": 0.8,
            "rewritten_dense": 0.5,
            "answer_intent_dense": 0.2,
        },
        "lexical_b": {
            "original_keyword": 2.0,
            "original_dense": 0.8,
            "rewritten_dense": 0.4,
            "answer_intent_dense": 0.1,
        },
    }
    paths = [make_variant(label, weights) for label, weights in variants.items()]

    base_cfg = yaml.safe_load(BASE50.read_text(encoding="utf-8"))
    manifest = {
        "snapshot_date": str(date.today()),
        "full500_source": str(FULL500.relative_to(ROOT)),
        "full500_snapshot": str(snapshot_config.relative_to(ROOT)),
        "full500_sha256": sha256(snapshot_config),
        "full500_result": {
            "questions": 500,
            "mode": "no-correction",
            "correctness_pct": 60.60,
            "completeness_pct": 62.57,
            "combined_score": 55.18,
            "recall_pct": 61.12,
            "invalid_extra_docs": 0.18,
        },
        "fixed_50_source": str(BASE50.relative_to(ROOT)),
        "fixed_50_question_count": len(base_cfg["pipeline"]["question_ids"]),
        "fixed_50_question_ids": base_cfg["pipeline"]["question_ids"],
        "existing_50_baseline": {
            "run": "pageindex_balanced50_bge_rerank_question_only_llm_route_multiview_20260814",
            "correctness_pct": 64.0,
            "completeness_pct": 65.49,
            "combined_score": 59.14,
            "recall_pct": 60.87,
            "invalid_extra_docs": 0.23,
        },
        "experiments": [str(path.relative_to(ROOT)) for path in paths],
    }
    (SNAPSHOT_DIR / "BGE500_NO_CORRECTION_SNAPSHOT_20260818.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
