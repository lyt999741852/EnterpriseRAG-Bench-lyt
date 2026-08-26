"""Audit completed Semantic selector and generation failures offline.

Gold document IDs and answer facts are read only after evaluation to explain
failure layers.  This module must never be imported by the online pipeline.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from src.elasticsearch_backend import ElasticsearchBackend, ElasticsearchConfig


TARGET_BUCKETS = {"selector_drop", "generation_gap"}


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
    return {
        str(row["question_id"]): row
        for row in payload.get("questions", [])
        if isinstance(row, dict) and row.get("question_id")
    }


def document_ids(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    return [str(item) for item in value.get("document_ids", []) if item]


def expected_ranks(value: Any, expected: set[str]) -> dict[str, int]:
    ranks: dict[str, int] = {}
    for rank, doc_id in enumerate(document_ids(value), 1):
        if doc_id in expected and doc_id not in ranks:
            ranks[doc_id] = rank
    return ranks


def final_expected_chunk_ids(stage: Any, expected: set[str]) -> list[str]:
    if not isinstance(stage, dict):
        return []
    return [
        str(chunk_id)
        for chunk_id in stage.get("chunk_ids", [])
        if any(str(chunk_id).startswith(f"{doc_id}__") for doc_id in expected)
    ]


def diagnostic_layer(bucket: str, score: dict[str, Any]) -> str:
    """Describe observed output facts without guessing the root cause."""
    if bucket == "selector_drop":
        return "submitted_evidence_drop"
    if int(score.get("invalid_extra_docs") or 0) > 0:
        return "generation_with_extra_documents"
    if score.get("answer_correct") is True and float(score.get("document_recall_pct") or 0) == 100:
        return "correct_answer_low_completeness"
    return "answer_synthesis_gap"


def fetch_chunks(
    backend: ElasticsearchBackend | None, chunk_ids: list[str]
) -> list[dict[str, Any]]:
    if backend is None or not chunk_ids:
        return []
    response = backend._request(  # Offline exact-ID evidence inspection.
        "POST", f"/{backend.config.alias_name}/_mget", {"ids": chunk_ids}
    )
    chunks: list[dict[str, Any]] = []
    for row in response.get("docs", []):
        if not row.get("found"):
            continue
        source = row.get("_source", {})
        chunks.append({
            "chunk_id": str(source.get("chunk_id", row.get("_id", ""))),
            "document_id": str(source.get("doc_id", "")),
            "chunk_index": source.get("chunk_index"),
            "text": str(source.get("text", "")),
        })
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--traces", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--failure-layers", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        help="Optional completed-run config for exact final-chunk text lookup.",
    )
    args = parser.parse_args()

    questions = load_jsonl(args.questions)
    traces = load_jsonl(args.traces)
    answers = load_jsonl(args.answers)
    scores = score_rows(args.results)
    failure_payload = json.loads(args.failure_layers.read_text(encoding="utf-8"))
    failures = {
        str(row["question_id"]): row
        for row in failure_payload.get("rows", [])
        if isinstance(row, dict) and row.get("bucket") in TARGET_BUCKETS
    }
    if not failures:
        raise ValueError("failure report has no selector_drop or generation_gap rows")
    backend = None
    if args.config:
        config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
        backend = ElasticsearchBackend(ElasticsearchConfig(**config["elasticsearch"]))

    rows: list[dict[str, Any]] = []
    for question_id in sorted(failures):
        if any(question_id not in source for source in (questions, traces, answers, scores)):
            raise ValueError(f"incomplete artifacts for {question_id}")
        failure = failures[question_id]
        expected = {str(item) for item in failure.get("expected_document_ids", []) if item}
        trace = traces[question_id]
        stages = trace.get("retrieval_stages", {})
        stages = stages if isinstance(stages, dict) else {}
        rerank = stages.get("rerank", {})
        rerank = rerank if isinstance(rerank, dict) else {}
        raw_views: list[dict[str, Any]] = []
        for view in stages.get("views", []):
            ranks = expected_ranks(view, expected)
            if ranks:
                raw_views.append({
                    "view": str(view.get("view", "unknown")),
                    "query": str(view.get("query", "")),
                    "expected_document_ranks": ranks,
                })

        answer = answers[question_id]
        score = scores[question_id]
        bucket = str(failure["bucket"])
        final_stage = stages.get("final_before_generation")
        expected_chunk_ids = final_expected_chunk_ids(final_stage, expected)
        rows.append({
            "question_id": question_id,
            "bucket": bucket,
            "diagnostic_layer": diagnostic_layer(bucket, score),
            "question": str(questions[question_id].get("question", "")),
            "expected_document_ids": sorted(expected),
            "answer_facts": questions[question_id].get("answer_facts", []),
            "raw_expected_hits": raw_views,
            "pre_rerank_expected_ranks": expected_ranks(rerank.get("before"), expected),
            "post_rerank_expected_ranks": expected_ranks(rerank.get("after"), expected),
            "final_expected_ranks": expected_ranks(final_stage, expected),
            "final_expected_chunks": fetch_chunks(backend, expected_chunk_ids),
            "submitted_document_ids": document_ids(answer),
            "submitted_expected_ranks": expected_ranks(answer, expected),
            "answer": str(answer.get("answer", "")),
            "answer_correct": score.get("answer_correct"),
            "completeness_pct": score.get("completeness_pct"),
            "document_recall_pct": score.get("document_recall_pct"),
            "invalid_extra_docs": score.get("invalid_extra_docs"),
            "correctness_reasoning": str(score.get("correctness_reasoning", "")),
            "inferred_question_type": trace.get("inferred_question_type"),
            "question_type_source": trace.get("question_type_source"),
            "pageindex_plan": trace.get("plan"),
            "route_action": trace.get("route_action"),
            "selected_document_ids": trace.get("selected_document_ids", []),
            "missing_facets": trace.get("missing_facets", []),
            "coverage_complete": trace.get("coverage_complete"),
        })

    counts = Counter(row["diagnostic_layer"] for row in rows)
    report = {
        "schema_version": 1,
        "scope": "offline Semantic selector/generation audit",
        "question_count": len(rows),
        "layer_counts": dict(sorted(counts.items())),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in report if key != "rows"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
