#!/usr/bin/env bash
set -euo pipefail
APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/semantic30_r4_s2_parent_window_20260820"

if [ -f "$RUN/results.json" ]; then
  echo "RESULTS_ALREADY_PRESENT"
  exit 0
fi

/root/anaconda3/bin/python - "$RUN/answers.jsonl" <<'PY'
import json,sys
from pathlib import Path
rows=[json.loads(line) for line in Path(sys.argv[1]).read_text(encoding='utf-8').splitlines() if line.strip()]
ids={row.get('question_id') for row in rows}
print('answers',len(rows),'unique_ids',len(ids))
raise SystemExit(0 if len(rows)==30 and len(ids)==30 else 1)
PY

export LARK_API_KEY=lark
export LLM_PROVIDER=openai
export LLM_API_KEY="$LARK_API_KEY"
export LLM_MODEL_NAME=lark
export CHEAP_LLM_MODEL_NAME=lark
export LLM_API_BASE=http://10.72.100.35:7777/v1
cd "$APP/EnterpriseRAG-Bench"
nohup /root/anaconda3/bin/python -m src.scripts.answer_evaluation.metrics_based_eval \
  --questions-file "$APP/questions.jsonl" \
  --answers-file "$RUN/answers.jsonl" \
  --results-file "$RUN/results.json" \
  --parallelism 2 --no-correction --resume > "$RUN/score.log" 2>&1 < /dev/null &
echo $! > "$RUN/score.pid"
echo "SCORE_PID=$(cat "$RUN/score.pid")"
