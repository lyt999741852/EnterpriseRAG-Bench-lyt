#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
NAME=semantic30_r4_baseline_off_20260820
RUN="$APP/outputs/$NAME"
CONFIG="$APP/configs/eval_$NAME.yaml"
SOURCE="$APP/configs/eval_pageindex_ab50_semantic_consensus_20260820_r3_off.yaml"

python - "$SOURCE" "$CONFIG" <<'PY'
import sys
from copy import deepcopy
from pathlib import Path
import yaml

source, target = map(Path, sys.argv[1:])
qids = [
    "qst_0176", "qst_0180", "qst_0184", "qst_0188", "qst_0192",
    "qst_0196", "qst_0200", "qst_0204", "qst_0208", "qst_0212",
    "qst_0216", "qst_0220", "qst_0224", "qst_0228", "qst_0232",
    "qst_0236", "qst_0240", "qst_0244", "qst_0248", "qst_0252",
    "qst_0256", "qst_0260", "qst_0264", "qst_0268", "qst_0272",
    "qst_0276", "qst_0177", "qst_0179", "qst_0182", "qst_0189",
]
cfg = deepcopy(yaml.safe_load(source.read_text(encoding="utf-8")))
cfg["pipeline"]["name"] = "semantic30_r4_baseline_off_20260820"
cfg["pipeline"]["question_ids"] = qids
cfg["pipeline"]["resume"] = False
cfg["pipeline"]["resume_legacy"] = False
cfg["pipeline"]["question_parallelism"] = 1
cfg["pageindex"]["enabled"] = False
cfg["pageindex"]["cache_dir"] = ".pageindex_cache/semantic30_r4_baseline_off_20260820"
target.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
print(target)
PY

mkdir -p "$RUN"
if [ -f "$RUN/run.pid" ] && kill -0 "$(cat "$RUN/run.pid")" 2>/dev/null; then
  echo "ALREADY_RUNNING PID=$(cat "$RUN/run.pid")"
  exit 0
fi

export LARK_API_KEY=lark
export EMBEDDING_API_KEY=123456
export TRANSFORMERS_OFFLINE=1
export QUESTION_PARALLELISM=1
cd "$APP"
nohup /root/anaconda3/envs/embedding_test/bin/python -u -m src.pipeline "$CONFIG" > "$RUN/pipeline.log" 2>&1 < /dev/null &
echo $! > "$RUN/run.pid"

nohup bash -c '
  set -u
  while true; do
    if [ -s "$0/answers.jsonl" ] && [ "$(wc -l < "$0/answers.jsonl")" -ge 30 ]; then
      export LLM_PROVIDER=openai
      export LLM_API_KEY="$LARK_API_KEY"
      export LLM_MODEL_NAME=lark
      export CHEAP_LLM_MODEL_NAME=lark
      export LLM_API_BASE=http://10.72.100.35:7777/v1
      cd "$1/EnterpriseRAG-Bench"
      /root/anaconda3/bin/python -m src.scripts.answer_evaluation.metrics_based_eval \
        --questions-file "$1/questions.jsonl" \
        --answers-file "$0/answers.jsonl" \
        --results-file "$0/results.json" \
        --parallelism 2 --no-correction --resume > "$0/score.log" 2>&1
      break
    fi
    sleep 20
  done
' "$RUN" "$APP" > "$RUN/score_watch.log" 2>&1 < /dev/null &
echo "PIPELINE_PID=$(cat "$RUN/run.pid")"
echo "RUN=$RUN"
