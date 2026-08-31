"""Fixed-trace O4 document-level soft pooling replay.

The baseline final-before-generation chunks are never removed. For each cap,
append at most N representative chunks from rerank candidates belonging to
previously unseen documents. This tests document diversity without LLM, ES,
reranker, PageIndex, or gold-driven selection.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


DOC_RE = re.compile(r"(dsid_[0-9a-f]+)__", re.IGNORECASE)


def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[str(row["question_id"])] = row
    return rows


def chunks(stage: Any) -> list[str]:
    if isinstance(stage, dict) and isinstance(stage.get("chunk_ids"), list):
        return [str(value) for value in stage["chunk_ids"] if value]
    return []


def doc_id(chunk_id: str) -> str:
    match = DOC_RE.match(str(chunk_id))
    return match.group(1) if match else ""


def hit(values: list[str], expected: set[str]) -> bool:
    return any(doc_id(value) in expected for value in values)


def pool(baseline: list[str], rerank: list[str], extra_docs: int) -> tuple[list[str], list[str]]:
    result = list(baseline)
    seen_chunks = set(result)
    seen_docs = {doc_id(value) for value in result if doc_id(value)}
    added_docs: list[str] = []
    for value in rerank:
        if value in seen_chunks:
            continue
        candidate_doc = doc_id(value)
        if not candidate_doc or candidate_doc in seen_docs:
            continue
        result.append(value)
        seen_chunks.add(value)
        seen_docs.add(candidate_doc)
        added_docs.append(candidate_doc)
        if len(added_docs) >= max(0, extra_docs):
            break
    return result, added_docs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--traces", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--caps", default="1,2,3")
    args = parser.parse_args()

    questions = load_jsonl(args.questions)
    traces = load_jsonl(args.traces)
    caps = [int(value) for value in args.caps.split(",") if value.strip()]
    common = sorted(set(questions) & set(traces))
    if not common:
        raise ValueError("no common questions and traces")

    rows: list[dict[str, Any]] = []
    for qid in common:
        question = questions[qid]
        trace = traces[qid]
        expected = {str(value) for value in question.get("expected_doc_ids", []) if value}
        stages = trace.get("retrieval_stages") or {}
        baseline = chunks(stages.get("final_before_generation"))
        rerank_stage = stages.get("rerank")
        rerank = chunks(rerank_stage.get("after") if isinstance(rerank_stage, dict) else rerank_stage)
        row: dict[str, Any] = {
            "question_id": qid,
            "question_type": question.get("question_type"),
            "expected_document_count": len(expected),
            "baseline_chunk_count": len(baseline),
            "baseline_document_count": len({doc_id(value) for value in baseline if doc_id(value)}),
            "baseline_hit": hit(baseline, expected) if expected else None,
            "rerank_chunk_count": len(rerank),
            "caps": {},
        }
        for cap in caps:
            pooled, added_docs = pool(baseline, rerank, cap)
            row["caps"][str(cap)] = {
                "chunk_count": len(pooled),
                "document_count": len({doc_id(value) for value in pooled if doc_id(value)}),
                "added_document_ids": added_docs,
                "hit": hit(pooled, expected) if expected else None,
                "recovered": bool(expected) and not row["baseline_hit"] and hit(pooled, expected),
            }
        rows.append(row)

    def aggregate(group: list[dict[str, Any]], cap: int | None = None) -> dict[str, Any]:
        effective = [row for row in group if row["expected_document_count"] > 0]
        values = [
            (row["baseline_hit"] if cap is None else row["caps"][str(cap)]["hit"])
            for row in effective
        ]
        result: dict[str, Any] = {
            "question_count": len(group),
            "effective_target_count": len(effective),
            "recall": round(100.0 * sum(values) / len(values), 2) if values else None,
        }
        if cap is not None:
            result["recovered_count"] = sum(row["caps"][str(cap)]["recovered"] for row in effective)
            result["mean_added_docs"] = round(
                sum(len(row["caps"][str(cap)]["added_document_ids"]) for row in effective) / len(effective), 2
            ) if effective else None
            result["mean_added_chunks"] = result["mean_added_docs"]
        return result

    by_type: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_type[str(row.get("question_type") or "unknown")].append(row)
    report = {
        "schema_version": 1,
        "scope": "O4 fixed trace document-level soft pooling replay",
        "question_count": len(rows),
        "caps": caps,
        "aggregate": {
            "baseline": aggregate(rows),
            **{f"soft_pool_{cap}": aggregate(rows, cap) for cap in caps},
        },
        "by_question_type": {
            qtype: {
                "baseline": aggregate(group),
                **{f"soft_pool_{cap}": aggregate(group, cap) for cap in caps},
            }
            for qtype, group in sorted(by_type.items())
        },
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "rows"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
