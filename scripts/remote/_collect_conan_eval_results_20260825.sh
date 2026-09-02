set -u
APP=/opt/enterprise-rag-bench/app
for run in \
  pageindex_balanced50_q3emb_20260812 \
  pageindex_balanced50_q3emb_rerank_20260812 \
  pageindex_stratified100_qwen3_v3_p0_chain_20260816 \
  pageindex_stratified100_qwen3_v3_p0_r1_nocollapse_20260817 \
  pageindex_stratified100_qwen3_v3_p0_r2_candidate_pool_20260817; do
  result="$APP/outputs/$run/results.json"
  if [ -f "$result" ]; then
    /root/anaconda3/bin/python - "$run" "$result" <<'PY'
import json, sys
run, path = sys.argv[1:]
d = json.load(open(path, encoding="utf-8"))
s = d.get("aggregate_stats", d)
keys = ["total_questions", "average_correctness_pct", "average_completeness_pct", "combined_correctness_completeness_score", "average_recall_pct", "average_invalid_extra_docs"]
print(run, json.dumps({k:s.get(k) for k in keys}, ensure_ascii=False))
PY
  else
    echo "$run MISSING"
  fi
done
