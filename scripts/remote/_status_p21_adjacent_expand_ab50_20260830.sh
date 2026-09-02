set -u
RUN=/opt/enterprise-rag-bench/app/outputs/p21_adjacent_expand_ab50_20260830
echo '=== STATUS ==='
if [ -f "$RUN/run.pid" ]; then
  pid=$(cat "$RUN/run.pid")
  echo "pid=$pid"
  kill -0 "$pid" 2>/dev/null && echo running || echo exited
fi
for f in answers.jsonl pipeline.log; do
  if [ -f "$RUN/$f" ]; then echo "$f lines=$(wc -l < "$RUN/$f") bytes=$(wc -c < "$RUN/$f")"; fi
done
echo '=== LOG TAIL ==='
tail -n 35 "$RUN/pipeline.log" 2>/dev/null || true
