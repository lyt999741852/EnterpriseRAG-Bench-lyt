"""Offline screen for original BM25+dense union, multiview append, and admission reserve.

The replay uses the completed F500 route trace and O0 funnel only.  It makes no
ES, embedding, reranker, PageIndex, or LLM calls.  The original keyword and
question-dense views are kept as the base order; additional views are appended
without re-RRFing the base.  The admission variants append a small reserve to
the recorded final-before-generation document set.
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
    rows: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[str(row["question_id"])] = row
    return rows


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def doc_id(value: str) -> str:
    match = DOC_RE.match(str(value))
    return match.group(1) if match else ""


def chunks(view: dict[str, Any]) -> list[str]:
    values = view.get("chunk_ids")
    return [str(value) for value in values if value] if isinstance(values, list) else []


def docs_in_order(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        current = doc_id(value)
        if current and current not in seen:
            seen.add(current)
            result.append(current)
    return result


def append_unique(base: list[str], groups: list[list[str]], limit: int) -> list[str]:
    result = list(base)
    seen = set(result)
    for group in groups:
        for value in group:
            if value in seen:
                continue
            result.append(value)
            seen.add(value)
            if len(result) >= limit:
                return result
    return result


def rrf_fuse(groups: list[tuple[list[str], float]], rrf_k: int = 60) -> list[str]:
    scores: dict[str, float] = defaultdict(float)
    first_seen: dict[str, int] = {}
    position = 0
    for values, weight in groups:
        for rank, value in enumerate(values, 1):
            scores[value] += float(weight) / (rrf_k + rank)
            if value not in first_seen:
                first_seen[value] = position
                position += 1
    return sorted(scores, key=lambda value: (-scores[value], first_seen[value]))


def first_doc_rank(values: list[str], expected: set[str]) -> int | None:
    for rank, value in enumerate(docs_in_order(values), 1):
        if value in expected:
            return rank
    return None


def hit_at(values: list[str], expected: set[str], limit: int) -> bool:
    return bool(set(docs_in_order(values[:limit])) & expected)


def metric(rows: list[dict[str, Any]], key: str, limits: tuple[int, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {"question_count": len(rows)}
    for limit in limits:
        values = [row[key]["hit_at"].get(str(limit), False) for row in rows]
        result[f"recall_at_{limit}"] = round(100.0 * sum(values) / len(values), 2) if values else None
    ranks = [row[key]["first_doc_rank"] for row in rows if row[key]["first_doc_rank"] is not None]
    result["mean_first_doc_rank"] = round(sum(ranks) / len(ranks), 2) if ranks else None
    result["ranked_question_count"] = len(ranks)
    return result


def evaluate(values: list[str], expected: set[str], limits: tuple[int, ...]) -> dict[str, Any]:
    return {
        "first_doc_rank": first_doc_rank(values, expected),
        "hit_at": {str(limit): hit_at(values, expected, limit) for limit in limits},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--traces", type=Path, required=True)
    parser.add_argument("--o0-funnel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--union-limit", type=int, default=240)
    parser.add_argument("--multiview-limit", type=int, default=360)
    parser.add_argument("--reserve-docs", type=int, default=8)
    parser.add_argument(
        "--scope",
        choices=("raw_miss", "effective"),
        default="raw_miss",
        help="raw_miss selects O0 raw-miss rows; effective includes every row with gold docs",
    )
    args = parser.parse_args()

    questions = load_jsonl(args.questions)
    traces = load_jsonl(args.traces)
    funnel = load_json(args.o0_funnel)
    funnel_rows = {str(row["question_id"]): row for row in funnel.get("rows", [])}

    selected: list[str] = []
    for qid, row in funnel_rows.items():
        if args.scope == "raw_miss" and row.get("bucket") != "raw_miss":
            continue
        if not row.get("expected_document_ids"):
            continue
        if qid in questions and qid in traces:
            selected.append(qid)
    selected.sort()
    if not selected:
        raise ValueError("no effective raw-miss rows found")

    limits = (30, 120, 240, 360)
    rows: list[dict[str, Any]] = []
    trigger_by_type: defaultdict[str, int] = defaultdict(int)
    for qid in selected:
        question = questions[qid]
        trace = traces[qid]
        expected = {str(value) for value in question.get("expected_doc_ids", []) if value}
        question_text = str(question.get("question") or "")
        keyword: list[str] = []
        original_dense: list[str] = []
        shadow_dense: list[list[str]] = []
        for view in (trace.get("retrieval_stages") or {}).get("views") or []:
            if not isinstance(view, dict):
                continue
            kind = str(view.get("view") or "")
            values = chunks(view)
            if kind == "keyword" and not keyword:
                keyword = values
            elif kind == "dense":
                query = str(view.get("query") or "")
                if not original_dense and query.casefold() == question_text.casefold():
                    original_dense = values
                elif query and query.casefold() != question_text.casefold():
                    shadow_dense.append(values)

        # The production retriever truncates the fused result at top_k=120;
        # keep that boundary for the baseline before testing an append-only union.
        base_rrf = rrf_fuse([(keyword, 1.2), (original_dense, 1.0)])[:120]
        # Append-only union preserves the existing base order and only fills its tail.
        original_union = append_unique(base_rrf, [keyword, original_dense], max(args.union_limit, 120))
        top8_keyword = set(docs_in_order(keyword[:8]))
        top8_dense = set(docs_in_order(original_dense[:8]))
        trigger = bool(keyword and original_dense and not top8_keyword.intersection(top8_dense))
        if trigger:
            trigger_by_type[str(question.get("question_type") or "unknown")] += 1
        triggered_multiview = append_unique(
            original_union,
            shadow_dense if trigger else [],
            max(args.multiview_limit, args.union_limit),
        )
        always_multiview = append_unique(
            original_union,
            shadow_dense,
            max(args.multiview_limit, args.union_limit),
        )

        funnel_row = funnel_rows[qid]
        stages = funnel_row.get("stage_document_ids") or {}
        final_docs = [str(value) for value in stages.get("final_before_generation", []) if value]
        reserve_source = triggered_multiview if trigger else original_union
        reserve_docs = docs_in_order(reserve_source)
        admitted = list(dict.fromkeys(final_docs))
        for value in reserve_docs:
            if value not in admitted:
                admitted.append(value)
            if len(admitted) >= len(final_docs) + max(0, args.reserve_docs):
                break
        row = {
            "question_id": qid,
            "question_type": question.get("question_type"),
            "expected_document_count": len(expected),
            "shadow_view_count": len(shadow_dense),
            "low_confidence_trigger": trigger,
            "base_rrf": evaluate(base_rrf, expected, limits),
            "original_union": evaluate(original_union, expected, limits),
            "triggered_multiview_append": evaluate(triggered_multiview, expected, limits),
            "always_multiview_append": evaluate(always_multiview, expected, limits),
            "final_before_generation": {
                "hit": bool(set(final_docs) & expected),
                "expected_count": len(set(final_docs) & expected),
                "document_count": len(final_docs),
            },
            "admission_reserve": {
                "hit": bool(set(admitted) & expected),
                "expected_count": len(set(admitted) & expected),
                "document_count": len(admitted),
                "reserve_docs": max(0, len(admitted) - len(final_docs)),
            },
        }
        rows.append(row)

    def aggregate(group: list[dict[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key in ("base_rrf", "original_union", "triggered_multiview_append", "always_multiview_append"):
            result[key] = metric(group, key, limits)
        final_hits = [bool(row["final_before_generation"]["hit"]) for row in group]
        reserve_hits = [bool(row["admission_reserve"]["hit"]) for row in group]
        result["final_before_generation_hit_rate"] = round(100.0 * sum(final_hits) / len(group), 2) if group else None
        result["admission_reserve_hit_rate"] = round(100.0 * sum(reserve_hits) / len(group), 2) if group else None
        result["admission_recovered"] = [
            row["question_id"] for row in group
            if not row["final_before_generation"]["hit"] and row["admission_reserve"]["hit"]
        ]
        return result

    by_type: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_type[str(row["question_type"] or "unknown")].append(row)
    report = {
        "schema_version": 1,
        "scope": f"O3.7 fixed O0 {args.scope} replay; original union, multiview append, admission reserve",
        "question_count": len(rows),
        "union_limit": args.union_limit,
        "multiview_limit": args.multiview_limit,
        "reserve_docs": args.reserve_docs,
        "trigger_counts_by_type": dict(sorted(trigger_by_type.items())),
        "aggregate": aggregate(rows),
        "by_question_type": {key: aggregate(value) for key, value in sorted(by_type.items())},
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"rows", "by_question_type"}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
