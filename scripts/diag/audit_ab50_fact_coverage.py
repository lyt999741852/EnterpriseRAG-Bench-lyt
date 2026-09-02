"""Offline gold-fact coverage funnel for a completed AB50 evaluation.

The official ``answer_facts`` and ``expected_doc_ids`` are used only after the
run has completed.  No output from this script is imported by the online
pipeline.  Stage coverage is document-level; lexical fact matching is reported
with scores and confidence so it can guide, but not replace, official scoring.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "because", "by", "for",
    "from", "how", "in", "is", "it", "of", "on", "or", "that", "the",
    "their", "there", "this", "to", "was", "were", "what", "when", "which",
    "with", "within", "would", "should", "than", "then", "into", "through",
    "does", "did", "do", "has", "have", "had", "only", "some", "more", "most",
    "among", "provided", "cases", "mentioned", "following", "question", "answer",
}
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_.:/%+@-]*", re.IGNORECASE)


def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        qid = str(row.get("question_id", ""))
        if not qid or qid in rows:
            raise ValueError(f"invalid or duplicate question_id at {path}:{number}")
        rows[qid] = row
    return rows


def load_scores(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("questions")
    if not isinstance(rows, list):
        raise ValueError(f"{path} has no questions list")
    return {str(row["question_id"]): row for row in rows if row.get("question_id")}


def stage_document_ids(trace: dict[str, Any]) -> dict[str, set[str]]:
    stages = trace.get("retrieval_stages", {})
    if not isinstance(stages, dict):
        stages = {}

    def docs(value: Any) -> set[str]:
        if not isinstance(value, dict):
            return set()
        return {str(item) for item in value.get("document_ids", []) if item}

    raw: set[str] = set()
    for view in stages.get("views", []):
        raw.update(docs(view))
    rerank = stages.get("rerank", {})
    rerank = rerank if isinstance(rerank, dict) else {}
    return {
        "raw_views": raw,
        "pre_rerank": docs(rerank.get("before")),
        "post_rerank": docs(rerank.get("after")),
        "final_before_generation": docs(stages.get("final_before_generation")),
        "submitted": docs(trace.get("_answer", {})),
    }


def tokens(value: str) -> set[str]:
    return {
        token.casefold()
        for token in TOKEN_RE.findall(value or "")
        if token.casefold() not in STOPWORDS and len(token) >= 2
    }


def fact_match(fact: str, text: str) -> dict[str, Any]:
    fact_tokens = tokens(fact)
    text_tokens = tokens(text)
    matched = sorted(fact_tokens & text_tokens)
    ratio = len(matched) / len(fact_tokens) if fact_tokens else 0.0
    numbers = {item for item in fact_tokens if any(char.isdigit() for char in item)}
    matched_numbers = sorted(numbers & text_tokens)
    # A high overlap or all numeric anchors plus a meaningful lexical overlap
    # is a useful deterministic indication that the document can support the
    # fact.  It is intentionally not called semantic entailment.
    supported = ratio >= 0.45 or (
        bool(numbers) and numbers.issubset(text_tokens) and ratio >= 0.30
    )
    return {
        "token_count": len(fact_tokens),
        "matched_token_count": len(matched),
        "overlap_pct": round(ratio * 100, 2),
        "matched_tokens": matched,
        "numeric_anchors": sorted(numbers),
        "matched_numeric_anchors": matched_numbers,
        "lexical_support": supported,
    }


def index_documents(corpus: Path, needed_ids: set[str] | None = None) -> dict[str, str]:
    indexed: dict[str, str] = {}
    for path in corpus.rglob("dsid_*__*"):
        if not path.is_file():
            continue
        match = re.match(r"(dsid_[0-9a-f]+)__", path.name, re.IGNORECASE)
        if not match:
            continue
        doc_id = match.group(1)
        if needed_ids is not None and doc_id not in needed_ids:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        indexed.setdefault(doc_id, text)
    return indexed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--traces", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    questions = load_jsonl(args.questions)
    traces = load_jsonl(args.traces)
    answers = load_jsonl(args.answers)
    scores = load_scores(args.results)
    common = sorted(set(questions) & set(traces) & set(answers) & set(scores))
    if not common:
        raise ValueError("no common completed question IDs")

    needed_ids = {
        str(doc_id)
        for qid in common
        for doc_id in questions[qid].get("expected_doc_ids", [])
        if doc_id
    }
    corpus = index_documents(args.corpus, needed_ids)
    rows: list[dict[str, Any]] = []
    bucket_counts: Counter[str] = Counter()
    stage_fact_counts: Counter[str] = Counter()
    first_loss_counts: Counter[str] = Counter()
    stage_order = ["raw_views", "pre_rerank", "post_rerank", "final_before_generation", "submitted"]

    for qid in common:
        question = questions[qid]
        expected = {str(item) for item in question.get("expected_doc_ids", []) if item}
        facts = [str(item) for item in question.get("answer_facts", []) if isinstance(item, str) and item.strip()]
        answer = answers[qid]
        stage_docs = stage_document_ids(traces[qid])
        stage_docs["submitted"] = {str(item) for item in answer.get("document_ids", []) if item}
        fact_rows: list[dict[str, Any]] = []
        for index, fact in enumerate(facts, 1):
            doc_matches: dict[str, dict[str, Any]] = {}
            for doc_id in sorted(expected):
                text = corpus.get(doc_id, "")
                if text:
                    doc_matches[doc_id] = fact_match(fact, text)
            supporting_docs = sorted(
                doc_id for doc_id, match in doc_matches.items() if match["lexical_support"]
            )
            stage_support = {
                stage: sorted(set(supporting_docs) & stage_docs[stage])
                for stage in stage_order
            }
            first_loss = "not_in_expected_corpus"
            if doc_matches and not supporting_docs:
                first_loss = "no_lexical_support_in_expected_docs"
            elif supporting_docs:
                first_loss = "answer_generation"
                for stage in stage_order:
                    if not stage_support[stage]:
                        first_loss = stage
                        break
            for stage in stage_order:
                if stage_support[stage]:
                    stage_fact_counts[stage] += 1
            fact_rows.append({
                "fact_index": index,
                "fact": fact,
                "supporting_expected_docs": supporting_docs,
                "document_match": doc_matches,
                "stage_supporting_docs": stage_support,
                "first_loss_stage": first_loss,
            })

        first_losses = [row["first_loss_stage"] for row in fact_rows]
        if not expected or not stage_docs["raw_views"] & expected:
            bucket = "raw_miss"
        elif not stage_docs["post_rerank"] & expected:
            bucket = "rerank_drop"
        elif not stage_docs["final_before_generation"] & expected:
            bucket = "pageindex_or_selector_drop"
        elif not stage_docs["submitted"] & expected:
            bucket = "citation_or_selector_drop"
        elif not bool(answer.get("answer", "").strip()):
            bucket = "generation_empty"
        else:
            score = scores[qid]
            bucket = "generation_or_fact_coverage_gap" if (
                not bool(score.get("answer_correct", False))
                or float(score.get("completeness_pct", 0.0) or 0.0) < 99.99
            ) else "fully_successful"
        bucket_counts[bucket] += 1
        for loss in first_losses:
            first_loss_counts[loss] += 1
        rows.append({
            "question_id": qid,
            "question_type": question.get("question_type"),
            "bucket": bucket,
            "expected_document_ids": sorted(expected),
            "stage_document_ids": {stage: sorted(stage_docs[stage]) for stage in stage_order},
            "answer_correct": bool(scores[qid].get("answer_correct", False)),
            "completeness_pct": float(scores[qid].get("completeness_pct", 0.0) or 0.0),
            "document_recall_pct": scores[qid].get("document_recall_pct"),
            "facts": fact_rows,
        })

    report = {
        "schema_version": 1,
        "scope": "AB50 offline official-answer-fact coverage funnel",
        "question_count": len(rows),
        "corpus_documents_indexed": len(corpus),
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "first_fact_loss_counts": dict(sorted(first_loss_counts.items())),
        "stage_fact_support_counts": dict(sorted(stage_fact_counts.items())),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in report if key != "rows"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
