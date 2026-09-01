cd /opt/enterprise-rag-bench/app
RUN=outputs/pageindex_o391_metadata_reserve_smoke20_20260901
wc -l $RUN/answers.jsonl $RUN/route_trace.jsonl 2>/dev/null || true
grep -h 'raw_hybrid_tail_reserve' $RUN/route_trace.jsonl 2>/dev/null | head -n 2 || true
