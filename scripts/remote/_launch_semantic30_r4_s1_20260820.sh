#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
NAME=semantic30_r4_s1_lexical_anchor_20260820
RUN="$APP/outputs/$NAME"
CONFIG="$APP/configs/eval_$NAME.yaml"
BASE_CONFIG="$APP/configs/eval_semantic30_r4_baseline_off_20260820.yaml"

/root/anaconda3/envs/embedding_test/bin/python - "$APP/src/pipeline.py" "$BASE_CONFIG" "$CONFIG" <<'PY'
import sys
from copy import deepcopy
from pathlib import Path
import yaml

code_path, base_path, config_path = map(Path, sys.argv[1:])
text = code_path.read_text(encoding="utf-8")
if "route_weight_cfg = multi_view_cfg.get(\"route_weights\", {}).get(" not in text:
    needle = '''            views = routes.get(retrieval_type_key, default_views)\n            result_lists: list[list] = []\n'''
    replacement = '''            views = routes.get(retrieval_type_key, default_views)\n            # Route-specific weights override the global defaults without\n            # changing any non-Semantic route.\n            global_weights = multi_view_cfg.get("weights", {})\n            route_weight_cfg = multi_view_cfg.get("route_weights", {}).get(\n                retrieval_type_key, {}\n            )\n\n            def view_weight(view_name: str, default: float) -> float:\n                return float(\n                    route_weight_cfg.get(\n                        view_name, global_weights.get(view_name, default)\n                    )\n                )\n\n            result_lists: list[list] = []\n'''
    if needle not in text:
        raise SystemExit("pipeline anchor not found")
    text = text.replace(needle, replacement, 1)
    replacements = {
        'multi_view_cfg.get("weights", {}).get("original_keyword", 1.2)': 'view_weight("original_keyword", 1.2)',
        'multi_view_cfg.get("weights", {}).get("original_dense", 1.0)': 'view_weight("original_dense", 1.0)',
        'multi_view_cfg.get("weights", {}).get("original_hybrid", 1.0)': 'view_weight("original_hybrid", 1.0)',
        '''multi_view_cfg.get("weights", {}).get(\n                                "rewritten_dense", 0.9\n                            )''': 'view_weight("rewritten_dense", 0.9)',
        '''multi_view_cfg.get("weights", {}).get(\n                                "answer_intent_dense", 0.4\n                            )''': 'view_weight("answer_intent_dense", 0.4)',
    }
    for old, new in replacements.items():
        if old not in text:
            raise SystemExit(f"weight anchor not found: {old}")
        text = text.replace(old, new, 1)
    code_path.write_text(text, encoding="utf-8")
    print("PIPELINE_ROUTE_WEIGHTS_PATCHED")
else:
    print("PIPELINE_ROUTE_WEIGHTS_ALREADY_PATCHED")

cfg = deepcopy(yaml.safe_load(base_path.read_text(encoding="utf-8")))
cfg["pipeline"]["name"] = "semantic30_r4_s1_lexical_anchor_20260820"
cfg["pipeline"]["resume"] = False
cfg["pipeline"]["resume_legacy"] = False
cfg["retrieval"]["multi_view"]["route_weights"] = {
    "semantic": {
        "original_keyword": 1.5,
        "original_dense": 1.0,
        "rewritten_dense": 0.8,
        "answer_intent_dense": 0.25,
    }
}
config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
print(config_path)
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
