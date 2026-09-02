#!/usr/bin/env bash
set -u
echo 'TIME'
date -Is
echo 'DNS'
getent hosts 10.72.100.35 || true
echo 'ROUTE'
ip route get 10.72.100.35 || true
echo 'PING'
ping -c 2 -W 2 10.72.100.35 || true
echo 'TCP_7777'
if command -v nc >/dev/null 2>&1; then
  nc -vz -w 5 10.72.100.35 7777 2>&1 || true
else
  timeout 5 bash -c '</dev/tcp/10.72.100.35/7777' 2>&1 || true
fi
echo 'HTTP'
curl -sv --connect-timeout 5 --max-time 15 http://10.72.100.35:7777/v1/models -o /tmp/llm_diag_body.out 2>&1 || true
echo 'LOCAL_7777_LISTENERS'
ss -lntp 2>/dev/null | grep ':7777' || true
echo 'LOCAL_LLM_PROCESSES'
ps -eo pid,stat,etime,%cpu,%mem,cmd | grep -Ei 'vllm|llm|7777|lark' | grep -v grep || true
echo 'BGE_SUPERVISOR'
RUN=/opt/enterprise-rag-bench/app/outputs/pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817
tail -n 15 "$RUN/resume_supervisor.log" 2>/dev/null || true
