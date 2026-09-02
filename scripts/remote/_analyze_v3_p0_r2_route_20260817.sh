#!/usr/bin/env bash
set -u
RUN=/opt/enterprise-rag-bench/app/outputs/pageindex_stratified100_qwen3_v3_p0_r2_candidate_pool_20260817
echo 'INFERRED_TYPES'
grep -o 'inferred_question_type[^,}]*' "$RUN/route_trace.jsonl" | sort | uniq -c || true
echo 'ROUTE_ACTIONS'
grep -o 'route_action[^,}]*' "$RUN/route_trace.jsonl" | sort | uniq -c || true
echo 'FALLBACK_MARKERS'
grep -oi 'fallback[^,}]*' "$RUN/route_trace.jsonl" | sort | uniq -c | head -30 || true
echo 'ERROR_MARKERS'
grep -oi 'error[^,}]*' "$RUN/route_trace.jsonl" | sort | uniq -c | head -30 || true
