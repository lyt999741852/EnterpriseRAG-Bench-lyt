set -euo pipefail
BASE=/opt/enterprise-rag-bench/app/outputs/pageindex_full500_bge_dpv4_20260831/results.json
CAND=/opt/enterprise-rag-bench/app/outputs/pageindex_o1_original_reserve_smoke20_20260831/results.json
python3 - "$BASE" "$CAND" <<'PY'
import json
import sys

def load(path):
    data = json.load(open(path, encoding="utf-8"))
    return {str(row["question_id"]): row for row in data["questions"]}

base = load(sys.argv[1])
cand = load(sys.argv[2])
ids = sorted(set(base) & set(cand))

def metric(rows):
    n = len(rows)
    correct = sum(bool(row.get("answer_correct")) for row in rows)
    completeness = sum(float(row.get("completeness_pct") or 0.0) for row in rows) / n
    combined = sum(
        float(row.get("completeness_pct") or 0.0)
        if row.get("answer_correct") else 0.0
        for row in rows
    ) / n
    recall_values = [float(row["document_recall_pct"]) for row in rows if row.get("document_recall_pct") is not None]
    invalid_values = [float(row["invalid_extra_docs"]) for row in rows if row.get("invalid_extra_docs") is not None]
    return {
        "n": n,
        "correctness": round(100.0 * correct / n, 2),
        "completeness": round(completeness, 2),
        "combined": round(combined, 2),
        "recall": round(sum(recall_values) / len(recall_values), 2) if recall_values else None,
        "invalid_extra_docs": round(sum(invalid_values) / len(invalid_values), 2) if invalid_values else None,
    }

print("baseline=" + repr(metric([base[qid] for qid in ids])))
print("o1=" + repr(metric([cand[qid] for qid in ids])))
print("deltas=" + repr({
    key: round(metric([cand[qid] for qid in ids])[key] - metric([base[qid] for qid in ids])[key], 2)
    for key in ("correctness", "completeness", "combined", "recall", "invalid_extra_docs")
}))
print("=== per_question_delta ===")
for qid in ids:
    b, c = base[qid], cand[qid]
    if (
        bool(b.get("answer_correct")) != bool(c.get("answer_correct"))
        or float(b.get("completeness_pct") or 0) != float(c.get("completeness_pct") or 0)
        or float(b.get("document_recall_pct") or 0) != float(c.get("document_recall_pct") or 0)
    ):
        print(qid, b.get("question_type"),
              f"correct {int(bool(b.get('answer_correct')))}->{int(bool(c.get('answer_correct')))}",
              f"complete {b.get('completeness_pct')}->{c.get('completeness_pct')}",
              f"recall {b.get('document_recall_pct')}->{c.get('document_recall_pct')}")
PY
