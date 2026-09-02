"""Prepare the fixed 30-question Semantic-only optimization baseline."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "configs/eval_pageindex_ab50_semantic_consensus_20260820_r3_off.yaml"
QIDS = [
    "qst_0176", "qst_0180", "qst_0184", "qst_0188", "qst_0192",
    "qst_0196", "qst_0200", "qst_0204", "qst_0208", "qst_0212",
    "qst_0216", "qst_0220", "qst_0224", "qst_0228", "qst_0232",
    "qst_0236", "qst_0240", "qst_0244", "qst_0248", "qst_0252",
    "qst_0256", "qst_0260", "qst_0264", "qst_0268", "qst_0272",
    "qst_0276", "qst_0177", "qst_0179", "qst_0182", "qst_0189",
]


def main() -> None:
    cfg = deepcopy(yaml.safe_load(SOURCE.read_text(encoding="utf-8")))
    name = "semantic30_r4_baseline_off_20260820"
    cfg["pipeline"]["name"] = name
    cfg["pipeline"]["question_ids"] = QIDS
    cfg["pipeline"]["resume"] = False
    cfg["pipeline"]["resume_legacy"] = False
    cfg["pipeline"]["question_parallelism"] = 1
    cfg["pageindex"]["enabled"] = False
    cfg["pageindex"]["cache_dir"] = f".pageindex_cache/{name}"
    target = ROOT / "configs" / f"eval_{name}.yaml"
    target.write_text(
        "# Fixed 30 Semantic questions; PageIndex OFF baseline for R4 optimization.\n"
        "# The question IDs are frozen and reused by every subsequent arm.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
