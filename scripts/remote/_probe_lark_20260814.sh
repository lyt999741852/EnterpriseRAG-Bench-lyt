#!/usr/bin/env bash
set -u
curl -sS --max-time 30 \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer lark' \
  http://10.72.100.35:7777/v1/chat/completions \
  -d '{"model":"lark","messages":[{"role":"user","content":"Reply with JSON only: {\"ok\":true}"}],"temperature":0,"max_tokens":80000}' \
  | head -c 2000
echo
