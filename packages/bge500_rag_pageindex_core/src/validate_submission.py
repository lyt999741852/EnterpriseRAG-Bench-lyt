"""Validate an EnterpriseRAG-Bench answer JSONL before evaluation/submission."""

from __future__ import annotations

import argparse
import json
import sys

from .evaluator import (
    compute_simple_metrics,
    filter_questions_by_source,
    load_answers_jsonl,
    load_questions,
    validate_answers,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", default="questions.jsonl")
    parser.add_argument("--answers", required=True)
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument(
        "--source-mode", choices=("exact", "contains"), default="exact"
    )
    parser.add_argument(
        "--allow-subset", action="store_true",
        help="Validate row structure without requiring every selected question.",
    )
    args = parser.parse_args(argv)

    questions = load_questions(args.questions)
    selected = filter_questions_by_source(
        questions, args.source, mode=args.source_mode
    )
    answers = load_answers_jsonl(args.answers)
    expected = None if args.allow_subset else set(selected)
    errors = validate_answers(answers, expected)
    metrics = compute_simple_metrics(answers, questions)

    report = {
        "valid": not errors,
        "answers": len(answers),
        "expected_questions": len(selected),
        "errors": errors,
        "simple_metrics": {
            key: metrics.get(key)
            for key in ("average_recall_pct", "average_invalid_extra_docs")
        },
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
