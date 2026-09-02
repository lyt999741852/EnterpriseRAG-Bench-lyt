#!/usr/bin/env bash
# Offline-resilient end-to-end run for the new 1792-dim index.
# Run on 10.72.100.29 from /opt/enterprise-rag-bench/app.
# It waits for/resumes the index build, runs the 50-question pipeline, then
# invokes the official scorer from the base conda environment.
set -uo pipefail

ROOT="/opt/enterprise-rag-bench/app"
INDEX="enterprise-rag-qwen3-emb-v1"
ALIAS="enterprise-rag-qwen3-emb"
CONFIG="configs/eval_pageindex_balanced50_q3emb.yaml"
BUILD_CONFIG="configs/full_es_qwen3_emb.yaml"
RUN_NAME="pageindex_balanced50_q3emb_20260805"
RUN_DIR="$ROOT/outputs/$RUN_NAME"
BUILD_LOG="$ROOT/outputs/build_qwen3_emb_20260805.log"
AUTO_LOG="$ROOT/outputs/q3emb50_automation.log"
MIN_COUNT=2000000
MAX_RESTARTS=5

mkdir -p "$ROOT/outputs" "$RUN_DIR"
cd "$ROOT" || exit 1

# Prevent two copies from running the same pipeline/scorer.
exec 9>"$ROOT/outputs/q3emb50_automation.lock"
if ! flock -n 9; then
  echo "[$(date -Is)] another q3emb50 automation is already running" >&2
  exit 0
fi

export TRANSFORMERS_OFFLINE=1
export CUDA_VISIBLE_DEVICES=2
export EMBEDDING_API_KEY=123456
export LARK_API_KEY=sentosa-qwen3-embedding

es_count() {
  curl -fsS --max-time 15 "http://127.0.0.1:9200/$INDEX/_count" 2>/dev/null \
    | /root/anaconda3/bin/python -c 'import json,sys; print(int(json.load(sys.stdin).get("count",0)))' \
    2>/dev/null || echo 0
}

build_running() {
  pgrep -f "src.build_es_index $BUILD_CONFIG" >/dev/null 2>&1
}

start_build() {
  echo "[$(date -Is)] restarting full index build"
  nohup /root/anaconda3/envs/embedding_test/bin/python -u -m src.build_es_index "$BUILD_CONFIG" \
    >> "$BUILD_LOG" 2>&1 &
  echo "[$(date -Is)] build pid $!"
}

wait_for_index() {
  local restarts=0 count
  while true; do
    count="$(es_count)"
    echo "[$(date -Is)] index=$INDEX count=$count target=$MIN_COUNT"
    if [ "$count" -ge "$MIN_COUNT" ]; then
      echo "[$(date -Is)] index ready"
      return 0
    fi
    if ! build_running; then
      if [ "$restarts" -ge "$MAX_RESTARTS" ]; then
        echo "[$(date -Is)] build stopped with count=$count; restart limit reached" >&2
        return 1
      fi
      restarts=$((restarts + 1))
      start_build
    fi
    sleep 60
  done
}

answers_complete() {
  [ -f "$RUN_DIR/answers.jsonl" ] || return 1
  /root/anaconda3/bin/python - "$RUN_DIR/answers.jsonl" <<'PY'
import json, sys
p = sys.argv[1]
rows = [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()]
ids = {r.get("question_id") for r in rows}
print(f"answers={len(rows)} ids={len(ids)}")
raise SystemExit(0 if len(rows) == 50 and len(ids) == 50 else 1)
PY
}

run_pipeline() {
  echo "[$(date -Is)] starting 50-question RAG pipeline"
  source /root/anaconda3/etc/profile.d/conda.sh
  conda activate embedding_test
  python -u -m src.pipeline "$CONFIG" \
    >> "$ROOT/outputs/q3emb50_pipeline.log" 2>&1
  return $?
}

run_official_score() {
  echo "[$(date -Is)] starting official scorer in base environment"
  export LLM_PROVIDER=openai
  export LLM_API_BASE=http://10.72.100.35:7777/v1
  export LLM_API_KEY=sentosa-qwen3-embedding
  export LLM_MODEL_NAME=lark
  cd "$ROOT/EnterpriseRAG-Bench" || return 1
  /root/anaconda3/bin/python -m src.scripts.answer_evaluation.metrics_based_eval \
    --questions-file "$ROOT/questions.jsonl" \
    --answers-file "$RUN_DIR/answers.jsonl" \
    --results-file "$RUN_DIR/results.json" \
    --parallelism 2 --no-correction --resume \
    >> "$ROOT/outputs/q3emb50_official_eval.log" 2>&1
}

echo "[$(date -Is)] q3emb50 automation started"
wait_for_index || exit 2

if ! answers_complete; then
  run_pipeline || {
    echo "[$(date -Is)] pipeline failed; rerun is safe because resume=true" >&2
    exit 3
  }
fi

if [ ! -s "$RUN_DIR/results.json" ]; then
  run_official_score || exit 4
fi

echo "[$(date -Is)] q3emb50 automation complete"
echo "results: $RUN_DIR/results.json"
