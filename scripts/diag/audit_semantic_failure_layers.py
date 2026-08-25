"""Classify an offline Semantic evaluation run by the first failed RAG layer.

This diagnostic is deliberately offline: it uses ``expected_doc_ids`` only after
an evaluation run has finished.  It must never be imported by the retrieval or
generation pipeline.

Example (run on the machine that owns the completed S1 artifacts)::

    python scripts/diag/audit_semantic_failure_layers.py \
      --questions questions.jsonl \
      --traces outputs/semantic30_r4_s1_lexical_anchor_20260820/route_trace.jsonl \
      --answers outputs/semantic30_r4_s1_lexical_anchor_20260820/answers.jsonl \
      --results outputs/semantic30_r4_s1_lexical_anchor_20260820/results.json \
      --output outputs/semantic30_r4_s1_lexical_anchor_20260820/failure_layers.json
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
        question_id = row.get("question_id")
        if not question_id:
            raise ValueError(f"{path}:{line_number} has no question_id")
        if question_id in rows:
            raise ValueError(f"{path}:{line_number} repeats question_id {question_id}")
        rows[question_id] = row
    return rows


def document_ids(stage: Any) -> set[str]:
    if not isinstance(stage, dict):
        return set()
    values = stage.get("document_ids", [])
    return {str(value) for value in values if value}


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


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes"}


def classify(
    question_id: str,
    expected_document_ids: set[str],
    trace: dict[str, Any],
    answer: dict[str, Any],
    score: dict[str, Any],
) -> dict[str, Any]:
    stages = trace.get("retrieval_stages", {})
    if not isinstance(stages, dict):
        stages = {}

    views = stages.get("views", [])
    raw_view_documents: set[str] = set()
    view_hits: list[str] = []
    if isinstance(views, list):
        for view in views:
            docs = document_ids(view)
            raw_view_documents.update(docs)
            if docs & expected_document_ids:
                view_hits.append(str(view.get("view", "unknown")))

    rerank = stages.get("rerank", {})
    if not isinstance(rerank, dict):
        rerank = {}
    pre_rerank_documents = document_ids(rerank.get("before"))
    post_rerank_documents = document_ids(rerank.get("after"))
    final_context_documents = document_ids(stages.get("final_before_generation"))
    submitted_documents = document_ids(answer)

    raw_hit = bool(raw_view_documents & expected_document_ids)
    pre_rerank_hit = bool(pre_rerank_documents & expected_document_ids)
    post_rerank_hit = bool(post_rerank_documents & expected_document_ids)
    final_context_hit = bool(final_context_documents & expected_document_ids)
    submitted_hit = bool(submitted_documents & expected_document_ids)
    answer_correct = bool_value(score.get("answer_correct", False))
    completeness_pct = float(score.get("completeness_pct", 0.0) or 0.0)
    initially_dropped = raw_hit and (not pre_rerank_hit or not post_rerank_hit)
    recovered_after_initial_drop = (
        initially_dropped
        and final_context_hit
        and submitted_hit
        and answer_correct
        and completeness_pct >= 99.99
    )

    # The bucket names are mutually exclusive.  More granular stage booleans
    # remain in each row so an analyst can distinguish RRF fusion from rerank.
    if not raw_hit:
        bucket = "raw_miss"
    elif initially_dropped and not recovered_after_initial_drop:
        bucket = "rrf_or_rerank_drop"
    elif not final_context_hit or not submitted_hit:
        bucket = "selector_drop"
    elif not answer_correct or completeness_pct < 99.99:
        bucket = "generation_gap"
    else:
        bucket = "fully_successful"

    return {
        "question_id": question_id,
        "bucket": bucket,
        "expected_document_ids": sorted(expected_document_ids),
        "raw_view_hit": raw_hit,
        "raw_view_hit_names": view_hits,
        "pre_rerank_hit": pre_rerank_hit,
        "post_rerank_hit": post_rerank_hit,
        "recovered_after_initial_drop": recovered_after_initial_drop,
        "final_context_hit": final_context_hit,
        "submitted_document_hit": submitted_hit,
        "answer_correct": answer_correct,
        "completeness_pct": completeness_pct,
        "document_recall_pct": score.get("document_recall_pct"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--traces", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--question-id",
        action="append",
        dest="question_ids",
        help="Limit the report to an ID; pass the option again for additional IDs.",
    )
    args = parser.parse_args()

    questions = load_jsonl(args.questions)
    traces = load_jsonl(args.traces)
    answers = load_jsonl(args.answers)
    scores = score_rows(args.results)
    # A completed evaluation artifact is the authoritative default scope.  This
    # prevents a fixed Semantic run from accidentally iterating unrelated
    # questions in the corpus that were never scored (or have no offline gold).
    selected_ids = (
        set(args.question_ids)
        if args.question_ids
        else set(traces) & set(answers) & set(scores)
    )
    if not selected_ids:
        raise ValueError("no completed question IDs were found in the evaluation artifacts")

    rows: list[dict[str, Any]] = []
    missing: dict[str, list[str]] = {}
    for question_id in sorted(selected_ids):
        question = questions.get(question_id)
        if not question:
            missing.setdefault("questions", []).append(question_id)
            continue
        expected = {str(value) for value in question.get("expected_doc_ids", []) if value}
        if not expected:
            raise ValueError(f"question {question_id} has no expected_doc_ids")
        for name, collection in (("traces", traces), ("answers", answers), ("scores", scores)):
            if question_id not in collection:
                missing.setdefault(name, []).append(question_id)
        if any(question_id in ids for ids in missing.values()):
            continue
        rows.append(classify(
            question_id, expected, traces[question_id], answers[question_id], scores[question_id]
        ))

    if missing:
        details = "; ".join(f"{name}={','.join(ids)}" for name, ids in missing.items())
        raise ValueError(f"incomplete artifacts: {details}")

    counts = Counter(row["bucket"] for row in rows)
    report = {
        "schema_version": 1,
        "question_count": len(rows),
        "bucket_counts": dict(sorted(counts.items())),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), **report["bucket_counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
