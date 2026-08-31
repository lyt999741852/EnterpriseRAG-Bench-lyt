set -euo pipefail
RUN=/opt/enterprise-rag-bench/app/outputs/pageindex_o1_original_reserve_smoke20_20260831
python3 - "$RUN/results.json" "$RUN/route_trace.jsonl" <<'PY'
import collections
import json
import sys

results = json.load(open(sys.argv[1], encoding="utf-8"))
traces = {}
with open(sys.argv[2], encoding="utf-8") as f:
    for line in f:
        if line.strip():
            row = json.loads(line)
            traces[str(row["question_id"])] = row

print("aggregate_stats=" + repr(results.get("aggregate_stats")))
print("question_type_stats=" + repr(results.get("question_type_stats")))
print("result_questions=" + str(len(results.get("questions", []))))

reserve_counts = []
route_actions = collections.Counter()
for qid, trace in sorted(traces.items()):
    route_actions[str(trace.get("route_action") or "unknown")] += 1
    reserve = trace.get("original_candidate_reserve") or {}
    reserve_counts.append(int(reserve.get("added_chunks", 0) or 0))
print("route_action_counts=" + repr(dict(sorted(route_actions.items()))))
print("reserve_added_total=" + str(sum(reserve_counts)))
print("reserve_questions=" + str(sum(value > 0 for value in reserve_counts)))
print("reserve_added_distribution=" + repr(dict(sorted(collections.Counter(reserve_counts).items()))))
PY
