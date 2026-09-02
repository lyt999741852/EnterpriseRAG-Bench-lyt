"""Compare O4.P smoke scores with the same questions from the F500 baseline."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def load(path: Path) -> dict[str, dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))["questions"]
    return {str(row["question_id"]): row for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    baseline = load(args.baseline)
    candidate = load(args.candidate)
    qids = sorted(candidate)

    def avg(rows: dict[str, dict], field: str, ids: list[str] = qids) -> float:
        return sum(float(rows[q].get(field, 0) or 0) for q in ids) / len(ids)

    def correct(rows: dict[str, dict], ids: list[str] = qids) -> int:
        return sum(bool(rows[q].get("answer_correct")) for q in ids)

    def line(label: str, rows: dict[str, dict], ids: list[str]) -> str:
        c = correct(rows, ids)
        comp = avg(rows, "completeness_pct", ids)
        combined = sum(
            (float(rows[q].get("completeness_pct", 0) or 0)
             if rows[q].get("answer_correct") else 0.0)
            for q in ids
        ) / len(ids)
        return (
            f"{label}: n={len(ids)} correctness={100*c/len(ids):.2f}% "
            f"completeness={comp:.2f}% combined={combined:.2f} "
            f"recall={avg(rows, 'document_recall_pct', ids):.2f}% "
            f"invalid_extra={avg(rows, 'invalid_extra_docs', ids):.2f}"
        )

    print(line("BASE", baseline, qids))
    print(line("O4P", candidate, qids))
    groups: defaultdict[str, list[str]] = defaultdict(list)
    for qid in qids:
        groups[str(candidate[qid].get("question_type") or "unknown")].append(qid)
    for question_type, ids in sorted(groups.items()):
        print(line(f"{question_type}", baseline, ids))
        print(line(f"{question_type}:O4P", candidate, ids))

    print("DELTAS")
    for qid in qids:
        b = baseline[qid]
        c = candidate[qid]
        print(
            qid,
            c.get("question_type"),
            f"correct={int(bool(b.get('answer_correct')))}->{int(bool(c.get('answer_correct')))}",
            f"comp={b.get('completeness_pct', 0)}->{c.get('completeness_pct', 0)}",
            f"recall={b.get('document_recall_pct', 0)}->{c.get('document_recall_pct', 0)}",
            f"extra={c.get('invalid_extra_docs', 0)}",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
