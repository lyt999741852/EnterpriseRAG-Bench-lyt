"""Create a sanitized, independent A3.2 end-to-end smoke config."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


QUESTION_IDS = [
    "qst_0176",
    "qst_0272",
    "qst_0177",
    "qst_0182",
    "qst_0220",
    "qst_0260",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--question-id", action="append")
    parser.add_argument("--preserve-question-ids", action="store_true")
    parser.add_argument("--name", default="semantic_a32_conflict_contract_smoke_20260826")
    args = parser.parse_args()
    config = yaml.safe_load(args.base.read_text(encoding="utf-8"))
    config["llm"]["api_key"] = ""
    config["llm"]["api_key_env"] = "LARK_API_KEY"
    config["pipeline"]["name"] = args.name
    if not args.preserve_question_ids:
        config["pipeline"]["question_ids"] = args.question_id or QUESTION_IDS
    config["pipeline"]["question_parallelism"] = 1
    config["pipeline"]["resume"] = False
    config["pipeline"]["resume_legacy"] = False
    config["pipeline"]["overwrite_index"] = False
    config["pageindex"]["enabled"] = False
    config["pageindex"]["cache_dir"] = ".pageindex_cache/semantic_a32_conflict_contract_smoke_20260826"
    config["evaluation"] = {"enabled": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
