set -u
curl -sS --max-time 5 http://127.0.0.1:18380/metrics 2>/dev/null | grep -Ei 'num_requests_running|num_requests_waiting|request_success_total|generation_tokens_total|prompt_tokens_total|time_to_first_token|kv_cache_usage|e2e_request_latency' | head -120 || true
