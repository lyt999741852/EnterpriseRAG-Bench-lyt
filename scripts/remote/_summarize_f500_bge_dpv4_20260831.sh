#!/usr/bin/env bash
set -euo pipefail

RUN_DIR="/opt/enterprise-rag-bench/app/outputs/pageindex_full500_bge_dpv4_20260831"
RESULTS="${RUN_DIR}/results.json"

python3 - "${RESULTS}" <<'PY'
import json
import math
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    data = json.load(f)

print("top_keys=" + ",".join(sorted(data.keys())))
print("aggregate_stats=" + repr(data.get("aggregate_stats")))
print("question_type_stats=" + repr(data.get("question_type_stats")))
for key in (
    "total_questions",
    "average_correctness_pct",
    "average_completeness_pct",
    "combined_correctness_completeness_score",
    "average_recall_pct",
    "average_invalid_extra_docs",
):
    print(f"{key}={data.get(key)!r}")

rows = data.get("results") or data.get("evaluations") or data.get("questions") or []
print(f"rows={len(rows)}")
if rows:
    print("first_row_keys=" + ",".join(sorted(rows[0].keys())))
    correct = [bool(r.get("answer_correct")) for r in rows if "answer_correct" in r]
    print(f"answer_correct_count={sum(correct)}")
    print(f"answer_correct_pct={100.0 * sum(correct) / len(correct):.4f}")

    def avg(name):
        vals = []
        for r in rows:
            v = r.get(name)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
                vals.append(float(v))
        return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)

    for name in ("completeness_pct", "document_recall_pct", "invalid_extra_docs"):
        value, count = avg(name)
        print(f"fallback_avg_{name}={value!r} count={count}")
PY
