#!/usr/bin/env bash
set -u
for endpoint in \
  http://10.72.55.209:7992/v1/models \
  http://10.72.100.35:7777/v1/models; do
  echo -n "$endpoint -> "
  curl -sS --connect-timeout 5 --max-time 15 -o /dev/null -w '%{http_code}' "$endpoint" || true
  echo
done
