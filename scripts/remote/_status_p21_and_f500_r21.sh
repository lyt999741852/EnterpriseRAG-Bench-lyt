set -u
echo '=== P2.1 ==='
RUN=/opt/enterprise-rag-bench/app/outputs/p21_adjacent_expand_ab50_20260830
if [ -f "$RUN/run.pid" ]; then pid=$(cat "$RUN/run.pid"); echo "pid=$pid"; kill -0 "$pid" 2>/dev/null && echo running || echo exited; fi
[ -f "$RUN/answers.jsonl" ] && echo "answers=$(wc -l < "$RUN/answers.jsonl")"
[ -f "$RUN/results.json" ] && echo results_present
tail -n 8 "$RUN/pipeline.log" 2>/dev/null || true
echo '=== F500 EXISTING PROCESSES ==='
ps -eo pid,etime,cmd | grep -E 'full500|src.pipeline' | grep -v grep | head -40 || true
echo '=== F500 OUTPUTS ==='
find /opt/enterprise-rag-bench/app/outputs -maxdepth 1 -type d -iname '*full500*' -printf '%f\n' 2>/dev/null | sort | tail -20
