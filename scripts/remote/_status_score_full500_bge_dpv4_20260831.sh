set -u
RUN=/opt/enterprise-rag-bench/app/outputs/pageindex_full500_bge_dpv4_20260831
echo '=== SCORE PROCESS ==='
ps -eo pid,etime,cmd | grep -E 'metrics_based_eval|answer_evaluation' | grep -v grep | head -20 || true
for f in results.json score.log; do
  if [ -f "$RUN/$f" ]; then
    echo "$f bytes=$(wc -c < "$RUN/$f") lines=$(wc -l < "$RUN/$f")"
    tail -n 12 "$RUN/$f"
  fi
done
