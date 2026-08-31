set -euo pipefail
F=/opt/enterprise-rag-bench/app/outputs/pageindex_full500_bge_dpv4_20260831/o0_funnel.json
python3 - "$F" <<'PY'
import collections
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    report = json.load(f)
rows = report["rows"]

print(f"questions={len(rows)}")
print("=== overall buckets ===")
for key, value in sorted(collections.Counter(r["bucket"] for r in rows).items()):
    print(f"{key}\t{value}\t{100.0*value/len(rows):.2f}%")

print("=== by question type ===")
by_type = collections.defaultdict(list)
for row in rows:
    by_type[str(row.get("question_type") or "unknown")].append(row)
for qtype in sorted(by_type):
    group = by_type[qtype]
    buckets = collections.Counter(r["bucket"] for r in group)
    correct = sum(bool(r.get("answer_correct")) for r in group)
    print(f"{qtype}\tn={len(group)}\tcorrect={correct}/{len(group)}\t" + ", ".join(f"{k}:{v}" for k,v in sorted(buckets.items())))

print("=== first fact loss by question type ===")
for qtype in sorted(by_type):
    counter = collections.Counter()
    for row in by_type[qtype]:
        for fact in row.get("facts", []):
            counter[str(fact.get("first_loss_stage") or "unknown")] += 1
    print(f"{qtype}\t" + ", ".join(f"{k}:{v}" for k,v in sorted(counter.items())))

print("=== raw miss question ids ===")
for qtype in sorted(by_type):
    ids = [r["question_id"] for r in by_type[qtype] if r["bucket"] == "raw_miss"]
    if ids:
        print(f"{qtype}\t{len(ids)}\t" + ",".join(ids))

print("=== rerank/pageindex/citation loss ids ===")
for bucket in ("rerank_drop", "pageindex_or_selector_drop", "citation_or_selector_drop"):
    ids = [r["question_id"] for r in rows if r["bucket"] == bucket]
    print(f"{bucket}\t{len(ids)}\t" + ",".join(ids[:80]))
PY
