set -euo pipefail

APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/semantic30_r4_s1_lexical_anchor_20260820"

/root/anaconda3/envs/embedding_test/bin/python - "$APP/questions.jsonl" "$RUN/route_trace.jsonl" "$RUN/results.json" <<'PY'
import json
import sys
from collections import Counter
from pathlib import Path

questions_path, traces_path, results_path = map(Path, sys.argv[1:])
ids = {
    "qst_0176", "qst_0180", "qst_0184", "qst_0188", "qst_0192", "qst_0196",
    "qst_0200", "qst_0204", "qst_0208", "qst_0212", "qst_0216", "qst_0220",
    "qst_0224", "qst_0228", "qst_0232", "qst_0236", "qst_0240", "qst_0244",
    "qst_0248", "qst_0252", "qst_0256", "qst_0260", "qst_0264", "qst_0268",
    "qst_0272", "qst_0276", "qst_0177", "qst_0179", "qst_0182", "qst_0189",
}
questions = {
    row["question_id"]: row
    for row in map(json.loads, questions_path.read_text(encoding="utf-8").splitlines())
    if row.get("question_id") in ids
}
traces = {
    row["question_id"]: row
    for row in map(json.loads, traces_path.read_text(encoding="utf-8").splitlines())
    if row.get("question_id") in ids
}
scores = {
    row["question_id"]: row
    for row in json.loads(results_path.read_text(encoding="utf-8"))["questions"]
    if row.get("question_id") in ids
}

counts = Counter()
examples = {"retrieval": [], "selection": [], "generation": []}
for qid in sorted(ids):
    gold = questions[qid]["expected_doc_ids"][0]
    trace = traces[qid]
    score = scores[qid]
    final_docs = set(
        trace.get("retrieval_stages", {}).get("final_before_generation", {}).get(
            "document_ids", []
        )
    )
    gold_in_context = gold in final_docs
    doc_recall = float(score.get("document_recall_pct", 0.0))
    correct = bool(score.get("answer_correct", False))
    complete = float(score.get("completeness_pct", 0.0))
    if not gold_in_context:
        bucket = "retrieval_context_missing"
        examples["retrieval"].append(qid)
    elif doc_recall < 100:
        bucket = "evidence_selection_or_citation_missing"
        examples["selection"].append(qid)
    elif not correct or complete < 99.99:
        bucket = "generation_or_fact_coverage_failure"
        examples["generation"].append(qid)
    else:
        bucket = "fully_successful"
    counts[bucket] += 1
    print(json.dumps({
        "qid": qid,
        "bucket": bucket,
        "gold_in_final_context": gold_in_context,
        "document_recall_pct": doc_recall,
        "answer_correct": correct,
        "completeness_pct": complete,
        "reason": score.get("correctness_reasoning", "")[:300],
    }, ensure_ascii=False))

print("SUMMARY", json.dumps(counts, ensure_ascii=False, sort_keys=True))
print("EXAMPLES", json.dumps(examples, ensure_ascii=False))
PY
