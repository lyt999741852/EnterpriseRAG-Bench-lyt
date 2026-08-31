"""Audit whether the completed run preserved the original BM25+dense views.

This is a read-only O1 check. It does not run retrieval or alter the pipeline;
it measures view presence and downstream PageIndex narrowing in existing traces.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        qid = str(row.get("question_id", ""))
        if not qid or qid in rows:
            raise ValueError(f"invalid or duplicate question_id at {path}:{line_no}")
        rows[qid] = row
    return rows


def doc_ids(items: Any) -> set[str]:
    if not isinstance(items, list):
        return set()
    return {str(item) for item in items if item}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traces", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--questions", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    traces = load_jsonl(args.traces)
    questions = load_jsonl(args.questions) if args.questions else {}
    score_payload = json.loads(args.results.read_text(encoding="utf-8"))
    scores = {
        str(row["question_id"]): row
        for row in score_payload.get("questions", [])
        if row.get("question_id")
    }
    common = sorted(set(traces) & set(scores))
    if not common:
        raise ValueError("no common trace/result question IDs")

    rows: list[dict[str, Any]] = []
    route_actions: Counter[str] = Counter()
    missing_original: Counter[str] = Counter()
    by_type: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)

    for qid in common:
        trace = traces[qid]
        stages = trace.get("retrieval_stages") or {}
        views = stages.get("views") if isinstance(stages, dict) else []
        view_names = [str(v.get("view")) for v in views if isinstance(v, dict)]
        originals = {name for name in view_names if name in {"keyword", "dense"}}
        # F500 records view names as keyword/dense; these are the original
        # query views because rewritten and intent views carry distinct names.
        if "keyword" not in originals:
            missing_original["keyword"] += 1
        if "dense" not in originals:
            missing_original["dense"] += 1

        rerank = stages.get("rerank") if isinstance(stages, dict) else {}
        rerank = rerank if isinstance(rerank, dict) else {}
        pre = doc_ids((rerank.get("before") or {}).get("document_ids"))
        post = doc_ids((rerank.get("after") or {}).get("document_ids"))
        final = doc_ids((stages.get("final_before_generation") or {}).get("document_ids"))
        raw = set()
        for view in views:
            if isinstance(view, dict):
                raw.update(doc_ids(view.get("document_ids")))
        action = str(trace.get("route_action") or "unknown")
        route_actions[action] += 1
        row = {
            "question_id": qid,
            # Benchmark type is used only for offline stratification; the
            # online route remains question-only and is preserved in trace.
            "question_type": questions.get(qid, {}).get("question_type")
            or scores[qid].get("question_type")
            or trace.get("inferred_question_type"),
            "answer_correct": bool(scores[qid].get("answer_correct")),
            "view_names": view_names,
            "original_keyword_present": "keyword" in originals,
            "original_dense_present": "dense" in originals,
            "raw_document_count": len(raw),
            "pre_rerank_document_count": len(pre),
            "post_rerank_document_count": len(post),
            "final_document_count": len(final),
            "pre_to_final_doc_overlap": len(pre & final) / len(pre) if pre else None,
            "route_action": action,
        }
        rows.append(row)
        by_type[str(row["question_type"] or "unknown")].append(row)

    type_summary: dict[str, dict[str, Any]] = {}
    for qtype, group in sorted(by_type.items()):
        type_summary[qtype] = {
            "count": len(group),
            "correct": sum(row["answer_correct"] for row in group),
            "missing_original_keyword": sum(not row["original_keyword_present"] for row in group),
            "missing_original_dense": sum(not row["original_dense_present"] for row in group),
            "route_actions": dict(sorted(Counter(row["route_action"] for row in group).items())),
            "mean_pre_to_final_doc_overlap": (
                sum(row["pre_to_final_doc_overlap"] for row in group if row["pre_to_final_doc_overlap"] is not None)
                / sum(row["pre_to_final_doc_overlap"] is not None for row in group)
                if any(row["pre_to_final_doc_overlap"] is not None for row in group)
                else None
            ),
        }

    report = {
        "schema_version": 1,
        "scope": "O1 read-only original BM25+dense preservation audit",
        "question_count": len(rows),
        "missing_original_view_counts": dict(sorted(missing_original.items())),
        "route_action_counts": dict(sorted(route_actions.items())),
        "question_type_summary": type_summary,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "rows"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
