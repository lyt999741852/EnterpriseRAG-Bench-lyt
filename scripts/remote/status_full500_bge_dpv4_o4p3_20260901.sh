set -u
RUN=/opt/enterprise-rag-bench/app/outputs/pageindex_full500_bge_dpv4_o4p3_20260901
echo '=== STATUS ==='
if [ -f "$RUN/run.pid" ]; then
  pid=$(cat "$RUN/run.pid")
  echo "pid=$pid"
  kill -0 "$pid" 2>/dev/null && echo running || echo exited
fi
for f in answers.jsonl pipeline.log results.json simple_metrics.json; do
  if [ -f "$RUN/$f" ]; then echo "$f lines=$(wc -l < "$RUN/$f") bytes=$(wc -c < "$RUN/$f")"; fi
done
echo '=== LOG TAIL ==='
tail -n 20 "$RUN/pipeline.log" 2>/dev/null || true
