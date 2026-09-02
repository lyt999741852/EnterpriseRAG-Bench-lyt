set -u
RUN=/opt/enterprise-rag-bench/app/outputs/pageindex_balanced50_conan448_rerank_question_only_llm_route_multiview_dpv4_20260828
PID=$(cat "$RUN/run.pid" 2>/dev/null || true)
echo "PID=$PID"
if [ -n "$PID" ]; then ps -p "$PID" -o pid=,etime=,stat=,pcpu=,pmem=,cmd= || true; fi
if [ -f "$RUN/answers.jsonl" ]; then wc -l "$RUN/answers.jsonl"; else echo 'answers.jsonl not yet present'; fi
tail -n 25 "$RUN/pipeline.log" 2>/dev/null || true
