"""Classify Basic questions in a completed evaluation into coverage failure layers.

Question type and score fields are used only after the run for offline analysis;
this script is not part of the RAG pipeline.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    return {
        str(row["question_id"]): row
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for row in [json.loads(line)]
    }


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    questions = load_jsonl(args.questions)
    answers = load_jsonl(args.answers)
    result_payload = json.loads(args.results.read_text(encoding="utf-8"))
    score_rows = {
        str(row["question_id"]): row
        for row in result_payload.get("questions", [])
        if isinstance(row, dict) and row.get("question_id")
    }

    rows: list[dict[str, Any]] = []
    for question_id, answer in answers.items():
        question = questions.get(question_id)
        score = score_rows.get(question_id)
        if not question or not score:
            continue
        if str(question.get("question_type", "")).lower() != "basic":
            continue
        correct = bool_value(score.get("answer_correct", False))
        completeness = float(score.get("completeness_pct", 0.0) or 0.0)
        recall = float(score.get("document_recall_pct", 0.0) or 0.0)
        invalid_extra = float(score.get("invalid_extra_docs", 0.0) or 0.0)
        if recall < 100.0:
            bucket = "retrieval_or_citation_gap"
        elif not correct or completeness < 99.99:
            bucket = "generation_coverage_gap"
        else:
            bucket = "fully_successful"
        rows.append({
            "question_id": question_id,
            "bucket": bucket,
            "answer_correct": correct,
            "completeness_pct": completeness,
            "document_recall_pct": recall,
            "invalid_extra_docs": invalid_extra,
            "submitted_document_count": len(answer.get("document_ids", [])),
            "correctness_reasoning": str(
                score.get("correctness_reasoning", "")
            )[:600],
        })

    counts = Counter(row["bucket"] for row in rows)
    report = {
        "schema_version": 1,
        "scope": "offline Basic-only coverage audit",
        "basic_question_count": len(rows),
        "bucket_counts": dict(sorted(counts.items())),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in report if key != "rows"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
