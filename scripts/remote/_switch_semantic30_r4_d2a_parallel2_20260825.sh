#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
NAME=semantic30_r4_d2a_wide_candidates_20260825
RUN="$APP/outputs/$NAME"
CONFIG="$APP/configs/eval_$NAME.yaml"
PID=$(cat "$RUN/run.pid")

echo "before_answers=$(wc -l < "$RUN/answers.jsonl")"
cp "$RUN/answers.jsonl" "$RUN/answers.before_parallel_resume.jsonl"
cp "$RUN/route_trace.jsonl" "$RUN/route_trace.before_parallel_resume.jsonl" 2>/dev/null || true
kill -TERM "$PID" 2>/dev/null || true
for _ in $(seq 1 30); do
  kill -0 "$PID" 2>/dev/null || break
  sleep 1
done
if kill -0 "$PID" 2>/dev/null; then
  echo "ERROR: pipeline did not stop cleanly; no restart performed"
  exit 1
fi

cp "$RUN/run_meta.json" "$RUN/run_meta.serial_before_parallel.json" 2>/dev/null || true
rm -f "$RUN/run_meta.json"
python - "$CONFIG" <<'PY'
from pathlib import Path
import sys

p = Path(sys.argv[1])
text = p.read_text(encoding="utf-8")
text = text.replace("  resume: false", "  resume: true")
text = text.replace("  resume_legacy: false", "  resume_legacy: true")
p.write_text(text, encoding="utf-8")
PY
printf '\n--- parallel-2 resume %s ---\n' "$(date -Is)" >> "$RUN/pipeline.log"

export LARK_API_KEY=lark
export EMBEDDING_API_KEY=123456
export TRANSFORMERS_OFFLINE=1
export QUESTION_PARALLELISM=2
cd "$APP"
nohup /root/anaconda3/envs/embedding_test/bin/python -u -m src.pipeline "$CONFIG" >> "$RUN/pipeline.log" 2>&1 < /dev/null &
NEW_PID=$!
echo "$NEW_PID" > "$RUN/run.pid"
echo "after_switch_pid=$NEW_PID"
echo "checkpoint_answers=$(wc -l < "$RUN/answers.jsonl")"
