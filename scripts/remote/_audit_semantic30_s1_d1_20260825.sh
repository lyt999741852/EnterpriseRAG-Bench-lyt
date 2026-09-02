set -euo pipefail

APP=/opt/enterprise-rag-bench/app
S1="$APP/outputs/semantic30_r4_s1_lexical_anchor_20260820"
D1="$APP/outputs/semantic30_r4_d1_document_first_20260821"

/root/anaconda3/envs/embedding_test/bin/python - "$APP/questions.jsonl" "$S1" "$D1" <<'PY'
import json
import sys
from collections import Counter
from pathlib import Path

questions_path, s1_dir, d1_dir = map(Path, sys.argv[1:])
ids = {
    "qst_0176", "qst_0180", "qst_0184", "qst_0188", "qst_0192", "qst_0196",
    "qst_0200", "qst_0204", "qst_0208", "qst_0212", "qst_0216", "qst_0220",
    "qst_0224", "qst_0228", "qst_0232", "qst_0236", "qst_0240", "qst_0244",
    "qst_0248", "qst_0252", "qst_0256", "qst_0260", "qst_0264", "qst_0268",
    "qst_0272", "qst_0276", "qst_0177", "qst_0179", "qst_0182", "qst_0189",
}

questions = {}
for line in questions_path.read_text(encoding="utf-8").splitlines():
    row = json.loads(line)
    if row.get("question_id") in ids:
        questions[row["question_id"]] = row

def load_jsonl(path):
    return {
        row["question_id"]: row
        for row in map(json.loads, path.read_text(encoding="utf-8").splitlines())
        if row.get("question_id") in ids
    }

s1_traces = load_jsonl(s1_dir / "route_trace.jsonl")
d1_traces = load_jsonl(d1_dir / "route_trace.jsonl")
s1_answers = load_jsonl(s1_dir / "answers.jsonl")
d1_answers = load_jsonl(d1_dir / "answers.jsonl")

counts = Counter()
rows = []
for qid in sorted(ids):
    gold = questions[qid]["expected_doc_ids"][0]
    s1 = s1_traces[qid]
    d1 = d1_traces[qid]
    s1_stages = s1.get("retrieval_stages", {})
    broad_docs = set(s1_stages.get("rerank", {}).get("before", {}).get("document_ids", []))
    s1_reranked = set(s1_stages.get("rerank", {}).get("after", {}).get("document_ids", []))
    s1_final = set(s1_stages.get("final_before_generation", {}).get("document_ids", []))
    d1_doc = d1.get("semantic_document_first", {}).get("selected_document_id")
    d1_final = set(d1.get("retrieval_stages", {}).get("final_before_generation", {}).get("document_ids", []))
    stage = (
        "A_missing_broad" if gold not in broad_docs else
        "B_lost_chunk_rerank" if gold not in s1_reranked else
        "C_lost_final_evidence" if gold not in s1_final else
        "D_gold_in_s1_final"
    )
    counts[stage] += 1
    d1_selected_gold = d1_doc == gold
    s1_answer_gold = gold in set(s1_answers[qid].get("document_ids", []))
    d1_answer_gold = gold in set(d1_answers[qid].get("document_ids", []))
    counts["D1_selected_gold" if d1_selected_gold else "D1_selected_wrong"] += 1
    counts["S1_output_gold" if s1_answer_gold else "S1_output_not_gold"] += 1
    counts["D1_output_gold" if d1_answer_gold else "D1_output_not_gold"] += 1
    rows.append({
        "qid": qid,
        "stage": stage,
        "s1_final_gold": gold in s1_final,
        "d1_selected_gold": d1_selected_gold,
        "s1_output_gold": s1_answer_gold,
        "d1_output_gold": d1_answer_gold,
        "d1_selected": d1_doc,
        "gold": gold,
    })

print("COUNTS", json.dumps(counts, ensure_ascii=False, sort_keys=True))
print("D1_WINS_OVER_S1")
for row in rows:
    if not row["s1_output_gold"] and row["d1_output_gold"]:
        print(json.dumps(row, ensure_ascii=False))
print("D1_LOSSES_FROM_S1")
for row in rows:
    if row["s1_output_gold"] and not row["d1_output_gold"]:
        print(json.dumps(row, ensure_ascii=False))
print("S1_BROAD_MISS")
for row in rows:
    if row["stage"] == "A_missing_broad":
        print(json.dumps(row, ensure_ascii=False))

raw_view_counts = Counter()
print("RAW_VIEW_AUDIT_FOR_BROAD_MISSES")
for row in rows:
    if row["stage"] != "A_missing_broad":
        continue
    qid = row["qid"]
    gold = row["gold"]
    views = s1_traces[qid].get("retrieval_stages", {}).get("views", [])
    hit_views = [
        view.get("view", "unknown")
        for view in views
        if gold in set(view.get("document_ids", []))
    ]
    raw_view_counts["raw_view_hit" if hit_views else "raw_view_miss"] += 1
    print(json.dumps({
        "qid": qid,
        "gold": gold,
        "hit_views": hit_views,
    }, ensure_ascii=False))
print("RAW_VIEW_COUNTS", json.dumps(raw_view_counts, ensure_ascii=False))
PY
