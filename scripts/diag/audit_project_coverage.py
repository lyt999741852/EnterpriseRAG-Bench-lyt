"""Audit Project-question document coverage after a completed evaluation.

This is an offline diagnostic.  It reads expected document IDs only after a
run has completed and must never be imported by the online RAG pipeline.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        question_id = str(row.get("question_id", ""))
        if not question_id or question_id in rows:
            raise ValueError(f"invalid or duplicate question_id at {path}:{line_number}")
        rows[question_id] = row
    return rows


def score_rows(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    questions = payload.get("questions")
    if not isinstance(questions, list):
        raise ValueError(f"{path} does not contain a questions list")
    return {
        str(row["question_id"]): row
        for row in questions
        if isinstance(row, dict) and row.get("question_id")
    }


def document_ids(value: Any) -> set[str]:
    if not isinstance(value, dict):
        return set()
    return {str(item) for item in value.get("document_ids", []) if item}


def bool_value(value: Any) -> bool:
    return value if isinstance(value, bool) else str(value).strip().lower() in {"true", "1", "yes"}


def matched(expected: set[str], value: Any) -> list[str]:
    return sorted(expected & document_ids(value))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--traces", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--question-id", action="append", dest="question_ids")
    args = parser.parse_args()

    questions = load_jsonl(args.questions)
    traces = load_jsonl(args.traces)
    answers = load_jsonl(args.answers)
    scores = score_rows(args.results)
    common_ids = set(traces) & set(answers) & set(scores)
    selected_ids = set(args.question_ids) if args.question_ids else common_ids
    rows: list[dict[str, Any]] = []

    for question_id in sorted(selected_ids):
        if question_id not in common_ids or question_id not in questions:
            raise ValueError(f"incomplete artifacts for {question_id}")
        question = questions[question_id]
        if str(question.get("question_type", "")).lower() != "project_related":
            raise ValueError(f"{question_id} is not a project_related question")
        expected = {str(item) for item in question.get("expected_doc_ids", []) if item}
        if not expected:
            raise ValueError(f"{question_id} has no expected_doc_ids")

        stages = traces[question_id].get("retrieval_stages", {})
        stages = stages if isinstance(stages, dict) else {}
        raw_ids: set[str] = set()
        for view in stages.get("views", []):
            raw_ids.update(document_ids(view))
        rerank = stages.get("rerank", {})
        rerank = rerank if isinstance(rerank, dict) else {}
        stage_matches = {
            "raw": sorted(expected & raw_ids),
            "pre_rerank": matched(expected, rerank.get("before")),
            "post_rerank": matched(expected, rerank.get("after")),
            "final_context": matched(expected, stages.get("final_before_generation")),
            "submitted": matched(expected, answers[question_id]),
        }
        score = scores[question_id]
        recall = float(score.get("document_recall_pct", 0.0) or 0.0)
        correct = bool_value(score.get("answer_correct", False))
        completeness = float(score.get("completeness_pct", 0.0) or 0.0)
        if recall < 99.99:
            bucket = "retrieval_or_citation_gap"
        elif not correct or completeness < 99.99:
            bucket = "generation_coverage_gap"
        else:
            bucket = "fully_successful"
        rows.append({
            "question_id": question_id,
            "bucket": bucket,
            "expected_document_ids": sorted(expected),
            "expected_document_count": len(expected),
            "matched_document_ids_by_stage": stage_matches,
            "raw_expected_recall_pct": round(100 * len(stage_matches["raw"]) / len(expected), 2),
            "submitted_expected_recall_pct": round(100 * len(stage_matches["submitted"]) / len(expected), 2),
            "answer_correct": correct,
            "completeness_pct": completeness,
            "document_recall_pct": recall,
            "invalid_extra_docs": float(score.get("invalid_extra_docs", 0.0) or 0.0),
            "correctness_reasoning": str(score.get("correctness_reasoning", ""))[:800],
        })

    counts = Counter(row["bucket"] for row in rows)
    report = {
        "schema_version": 1,
        "scope": "offline Project-only coverage audit",
        "project_question_count": len(rows),
        "bucket_counts": dict(sorted(counts.items())),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in report if key != "rows"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
