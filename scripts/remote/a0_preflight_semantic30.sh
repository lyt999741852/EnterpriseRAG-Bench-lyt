#!/usr/bin/env bash
# Read-only preflight for the Semantic30 A0 diagnostic.
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/semantic30_r4_s1_lexical_anchor_20260820"
INDEX=enterprise-rag-bge-small-v1

require_env() {
  if [ -z "${!1:-}" ]; then
    echo "MISSING_ENV=$1"
    exit 2
  fi
}

http_status() {
  local name="$1"
  local url="$2"
  local authorization="${3:-}"
  local code
  if [ -n "$authorization" ]; then
    code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 \
      -H "Authorization: Bearer $authorization" "$url" || true)
  else
    code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "$url" || true)
  fi
  echo "${name}_HTTP=${code:-000}"
}

require_env EMBEDDING_API_KEY
require_env LARK_API_KEY

http_status "BGE_ES_HEALTH" "http://127.0.0.1:9200/_cluster/health/$INDEX?timeout=10s"
http_status "BGE_ES_COUNT" "http://127.0.0.1:9200/$INDEX/_count"
http_status "RERANK" "http://10.72.55.209:7992/v1/models" "$EMBEDDING_API_KEY"
http_status "RESEARCH_EMBEDDING" "http://10.72.55.209:7993/v1/models" "$EMBEDDING_API_KEY"
http_status "LLM" "http://10.72.100.35:7777/v1/models" "$LARK_API_KEY"

if [ -s "$APP/.index_cache/full_es_bge_small/manifest.sqlite3" ]; then
  echo "MANIFEST=present"
  stat -c 'MANIFEST_BYTES=%s' "$APP/.index_cache/full_es_bge_small/manifest.sqlite3"
else
  echo "MANIFEST=missing_or_empty"
fi

for file in answers.jsonl route_trace.jsonl results.json; do
  if [ -s "$RUN/$file" ]; then
    echo "S1_${file}=present"
  else
    echo "S1_${file}=missing_or_empty"
  fi
done

if [ -f "$RUN/answers.jsonl" ]; then
  echo "S1_ANSWER_LINES=$(wc -l < "$RUN/answers.jsonl")"
fi
if [ -f "$RUN/route_trace.jsonl" ]; then
  echo "S1_TRACE_LINES=$(wc -l < "$RUN/route_trace.jsonl")"
fi
if [ -f "$RUN/results.json" ]; then
  python - "$RUN/results.json" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
questions = data.get("questions", [])
print(f"S1_SCORE_ROWS={len(questions) if isinstance(questions, list) else 0}")
PY
fi

pgrep -af 'src\.pipeline|metrics_based_eval' || echo 'ACTIVE_EVAL_PROCESSES=none'
