"""Prepare the fixed AB150 set: existing AB50 plus 100 evenly stratified new questions."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
questions = [json.loads(line) for line in (ROOT / "questions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
existing = [x.strip() for x in (ROOT / "configs/s3_ab50_question_ids_20260902.txt").read_text(encoding="utf-8").splitlines() if x.strip()]
existing_set = set(existing)
by_type: dict[str, list[str]] = defaultdict(list)
for row in questions:
    qid = str(row["question_id"])
    if qid not in existing_set:
        by_type[str(row.get("question_type") or "unknown")].append(qid)
for values in by_type.values():
    values.sort()

types = [
    "basic", "semantic", "intra_document_reasoning", "project_related", "constrained",
    "conflicting_info", "completeness", "miscellaneous", "high_level", "info_not_found",
]
target = {name: (9 if name == "high_level" else 11 if name == "basic" else 10) for name in types}
new: list[str] = []
for name in types:
    values = by_type[name]
    n = min(target[name], len(values))
    # Evenly spaced deterministic picks cover the type's qid range instead of
    # clustering on the first IDs.
    picked = []
    for i in range(n):
        idx = min(len(values) - 1, int((i + 0.5) * len(values) / n))
        if values[idx] not in picked:
            picked.append(values[idx])
    new.extend(picked)

combined = existing + new
if len(new) != 100 or len(combined) != 150 or len(set(combined)) != 150:
    raise SystemExit(f"unexpected sizes: existing={len(existing)} new={len(new)} combined={len(combined)}")
rows_by_id = {str(row["question_id"]): row for row in questions}
dist_existing = Counter(str(rows_by_id[q].get("question_type")) for q in existing)
dist_new = Counter(str(rows_by_id[q].get("question_type")) for q in new)
dist_combined = Counter(str(rows_by_id[q].get("question_type")) for q in combined)
(ROOT / "configs/s3_ab100_new_question_ids_20260902.txt").write_text("\n".join(new) + "\n", encoding="utf-8")
(ROOT / "configs/s3_ab150_question_ids_20260902.txt").write_text("\n".join(combined) + "\n", encoding="utf-8")
(ROOT / "configs/s3_ab150_sampling_manifest_20260902.json").write_text(json.dumps({
    "scope": "S3 fixed AB150",
    "existing_ab50_count": len(existing),
    "new_count": len(new),
    "combined_count": len(combined),
    "existing_distribution": dict(dist_existing),
    "new_distribution": dict(dist_new),
    "combined_distribution": dict(dist_combined),
    "new_question_ids": new,
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"existing": dict(dist_existing), "new": dict(dist_new), "combined": dict(dist_combined)}, ensure_ascii=False, indent=2))
