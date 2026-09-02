set -u
RUN=/opt/enterprise-rag-bench/app/outputs/pageindex_balanced50_conan448_rerank_question_only_llm_route_multiview_dpv4_20260828
while true; do
  PID=$(cat "$RUN/run.pid" 2>/dev/null || true)
  N=0
  if [ -f "$RUN/answers.jsonl" ]; then N=$(wc -l < "$RUN/answers.jsonl"); fi
  echo "$(date -Is) answers=$N pid=$PID"
  if [ "$N" -ge 50 ]; then break; fi
  if [ -n "$PID" ] && ! kill -0 "$PID" 2>/dev/null; then
    echo 'PIPELINE_EXITED_BEFORE_50'
    tail -n 60 "$RUN/pipeline.log" || true
    exit 1
  fi
  sleep 30
done
tail -n 40 "$RUN/pipeline.log" || true
