"""Fixed-trace replay for O2 low-confidence shadow candidate screening.

No model, ES, reranker, or PageIndex call is made. Existing F500 retrieval
view traces are re-fused with an always-on original keyword+dense base and a
bounded shadow union enabled only when the original top-8 document sets do not
overlap. This is an eligibility screen, not a causal end-to-end score.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
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


def doc_id(chunk_id: str) -> str:
    match = DOC_RE.match(str(chunk_id))
    return match.group(1) if match else ""


def view_chunks(view: dict[str, Any]) -> list[str]:
    values = view.get("chunk_ids")
    return [str(item) for item in values if item] if isinstance(values, list) else []


def rrf_fuse(groups: list[tuple[list[str], float]], rrf_k: int = 60) -> list[str]:
    scores: dict[str, float] = defaultdict(float)
    first_seen: dict[str, int] = {}
    position = 0
    for chunks, weight in groups:
        for rank, chunk in enumerate(chunks, 1):
            scores[chunk] += float(weight) / (rrf_k + rank)
            if chunk not in first_seen:
                first_seen[chunk] = position
                position += 1
    return sorted(scores, key=lambda chunk: (-scores[chunk], first_seen[chunk]))


def hit_at(chunks: list[str], expected: set[str], k: int) -> bool:
    return any(doc_id(chunk) in expected for chunk in chunks[:k])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--traces", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    questions = load_jsonl(args.questions)
    traces = load_jsonl(args.traces)
    common = sorted(set(questions) & set(traces))
    if not common:
        raise ValueError("no common question IDs")

    rows: list[dict[str, Any]] = []
    trigger_counts: Counter[str] = Counter()
    by_type: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    recovered: dict[str, list[str]] = {"at30": [], "at120": []}
    lost: dict[str, list[str]] = {"at30": [], "at120": []}

    for qid in common:
        question = questions[qid]
        trace = traces[qid]
        expected = {str(item) for item in question.get("expected_doc_ids", []) if item}
        views = (trace.get("retrieval_stages") or {}).get("views") or []
        original_keyword: list[str] = []
        original_dense: list[str] = []
        shadow_groups: list[list[str]] = []
        for view in views:
            if not isinstance(view, dict):
                continue
            kind = str(view.get("view") or "")
            chunks = view_chunks(view)
            if kind == "keyword" and not original_keyword:
                original_keyword = chunks
            elif kind == "dense":
                query = str(view.get("query") or "")
                if not original_dense and query.casefold() == str(question.get("question") or "").casefold():
                    original_dense = chunks
                elif query.casefold() != str(question.get("question") or "").casefold():
                    shadow_groups.append(chunks)

        kw_docs = {doc_id(chunk) for chunk in original_keyword[:8] if doc_id(chunk)}
        dense_docs = {doc_id(chunk) for chunk in original_dense[:8] if doc_id(chunk)}
        trigger = bool(original_keyword and original_dense and not kw_docs.intersection(dense_docs))
        if trigger:
            trigger_counts[str(question.get("question_type") or "unknown")] += 1

        base = rrf_fuse([
            (original_keyword, 1.2),
            (original_dense, 1.0),
        ])
        shadow = rrf_fuse([
            (original_keyword, 1.2),
            (original_dense, 1.0),
            *[(group[:40], 0.4) for group in shadow_groups],
        ]) if trigger else base
        append_shadow = list(base)
        seen_append = set(append_shadow)
        if trigger:
            for group in shadow_groups:
                for chunk in group[:40]:
                    if chunk in seen_append:
                        continue
                    append_shadow.append(chunk)
                    seen_append.add(chunk)
        row = {
            "question_id": qid,
            "question_type": question.get("question_type"),
            "expected_document_count": len(expected),
            "low_confidence_trigger": trigger,
            "original_keyword_chunks": len(original_keyword),
            "original_dense_chunks": len(original_dense),
            "shadow_view_count": len(shadow_groups),
            "base_hit_at_30": hit_at(base, expected, 30) if expected else None,
            "o2_hit_at_30": hit_at(shadow, expected, 30) if expected else None,
            "base_hit_at_120": hit_at(base, expected, 120) if expected else None,
            "o2_hit_at_120": hit_at(shadow, expected, 120) if expected else None,
            "base_hit_at_240": hit_at(base, expected, 240) if expected else None,
            "base_hit_at_1000": hit_at(base, expected, 1000) if expected else None,
            "append_hit_at_240": hit_at(append_shadow, expected, 240) if expected else None,
            "append_hit_at_1000": hit_at(append_shadow, expected, 1000) if expected else None,
        }
        rows.append(row)
        by_type[str(row["question_type"] or "unknown")].append(row)
        for cutoff in (30, 120):
            base_key = f"base_hit_at_{cutoff}"
            o2_key = f"o2_hit_at_{cutoff}"
            if row[base_key] is False and row[o2_key] is True:
                recovered[f"at{cutoff}"].append(qid)
            if row[base_key] is True and row[o2_key] is False:
                lost[f"at{cutoff}"].append(qid)

    def aggregate(group: list[dict[str, Any]]) -> dict[str, Any]:
        effective = [row for row in group if row["expected_document_count"] > 0]
        result: dict[str, Any] = {
            "count": len(group),
            "effective_target_count": len(effective),
            "trigger_count": sum(bool(row["low_confidence_trigger"]) for row in group),
        }
        for cutoff in (30, 120):
            for prefix in ("base", "o2"):
                values = [row[f"{prefix}_hit_at_{cutoff}"] for row in effective]
                result[f"{prefix}_recall_at_{cutoff}"] = round(
                    100.0 * sum(values) / len(values), 2
                ) if values else None
        for cutoff in (240, 1000):
            for prefix in ("base", "append"):
                values = [row[f"{prefix}_hit_at_{cutoff}"] for row in effective]
                result[f"{prefix}_recall_at_{cutoff}"] = round(
                    100.0 * sum(values) / len(values), 2
                ) if values else None
        return result

    report = {
        "schema_version": 1,
        "scope": "O2 fixed F500 trace replay; no model or retrieval calls",
        "question_count": len(rows),
        "trigger_counts_by_type": dict(sorted(trigger_counts.items())),
        "aggregate": aggregate(rows),
        "by_question_type": {
            qtype: aggregate(group) for qtype, group in sorted(by_type.items())
        },
        "recovered_at_30": recovered["at30"],
        "recovered_at_120": recovered["at120"],
        "lost_at_30": lost["at30"],
        "lost_at_120": lost["at120"],
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "rows"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
