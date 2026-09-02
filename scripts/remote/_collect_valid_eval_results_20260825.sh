set -u
APP=/opt/enterprise-rag-bench/app
for run in \
  pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817 \
  pageindex_balanced50_bge_rerank_question_only_llm_route_multiview_20260814 \
  pageindex_ab50_semantic_consensus_20260820_on \
  pageindex_ab50_semantic_consensus_20260820_off \
  pageindex_ab50_semantic_consensus_20260820_r3_on \
  pageindex_ab50_semantic_consensus_20260820_r3_off \
  semantic30_r4_baseline_off_20260820 \
  semantic30_r4_s1_lexical_anchor_20260820 \
  semantic30_r4_s2_parent_window_20260820 \
  semantic30_r4_s3_anchor_rescue_20260821 \
  semantic30_r4_d1_document_first_20260821 \
  semantic30_r4_d2a_wide_candidates_20260825; do
  result="$APP/outputs/$run/results.json"
  if [ -f "$result" ]; then
    /root/anaconda3/bin/python - "$run" "$result" <<'PY'
import json, sys
run, path = sys.argv[1:]
d = json.load(open(path, encoding="utf-8"))
s = d.get("aggregate_stats", d)
keys = [
    "total_questions", "average_correctness_pct", "average_completeness_pct",
    "combined_correctness_completeness_score", "average_recall_pct",
    "average_invalid_extra_docs",
]
print(run, json.dumps({k: s.get(k) for k in keys}, ensure_ascii=False))
PY
  else
    echo "$run MISSING"
  fi
done
