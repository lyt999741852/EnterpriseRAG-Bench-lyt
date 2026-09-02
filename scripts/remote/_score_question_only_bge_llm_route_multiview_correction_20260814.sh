#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
OFFICIAL="$APP/EnterpriseRAG-Bench"
RUN="$APP/outputs/pageindex_balanced50_bge_rerank_question_only_llm_route_multiview_20260814"
BUNDLE="$RUN/official_correction"

mkdir -p "$BUNDLE"
python "$APP/scripts/remote/_prepare_official_correction_bundle.py" \
  --questions-file "$APP/questions.jsonl" \
  --answers-file "$RUN/answers.jsonl" \
  --official-root "$OFFICIAL" \
  --bundle-dir "$BUNDLE" \
  --workers 8

export LLM_PROVIDER=openai
export LLM_API_KEY=lark
export LLM_MODEL_NAME=lark
export CHEAP_LLM_MODEL_NAME=lark
export LLM_API_BASE=http://10.72.100.35:7777/v1

cd "$OFFICIAL"
/root/anaconda3/bin/python -m src.scripts.answer_evaluation.metrics_based_eval \
  --questions-file "$BUNDLE/questions.jsonl" \
  --answers-file "$RUN/answers.jsonl" \
  --results-file "$BUNDLE/results.json" \
  --updated-questions-file "$BUNDLE/questions_updated.jsonl" \
  --uuid-index-cache-file "$BUNDLE/uuid_index.json" \
  --parallelism 4 --resume
