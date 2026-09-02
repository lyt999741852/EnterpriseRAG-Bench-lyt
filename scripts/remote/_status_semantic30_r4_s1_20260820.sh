#!/usr/bin/env bash
set -u
APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/semantic30_r4_s1_lexical_anchor_20260820"
if [ -f "$RUN/run.pid" ]; then
  pid=$(cat "$RUN/run.pid")
  echo "PID=$pid"
  ps -p "$pid" -o pid,stat,etime,%cpu,%mem,cmd --no-headers || echo PROCESS_NOT_RUNNING
fi
if [ -f "$RUN/answers.jsonl" ]; then echo -n 'ANSWERS='; wc -l < "$RUN/answers.jsonl"; fi
if [ -f "$RUN/results.json" ]; then
  python -c 'import json,sys; from pathlib import Path; d=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")); print("AGGREGATE="+json.dumps(d.get("aggregate_stats",{}),ensure_ascii=False)); print("QUESTION_TYPE_STATS="+json.dumps(d.get("question_type_stats",{}),ensure_ascii=False))' "$RUN/results.json"
fi
for f in pipeline.log score_watch.log score.log; do
  if [ -f "$RUN/$f" ]; then echo "---$f---"; tail -n 12 "$RUN/$f"; fi
done
