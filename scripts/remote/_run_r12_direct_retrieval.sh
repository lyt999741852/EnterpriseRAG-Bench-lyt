#!/usr/bin/env bash
set -euo pipefail
APP=/opt/enterprise-rag-bench/app
cd "$APP"
export TRANSFORMERS_OFFLINE=1
export EMBEDDING_API_KEY=123456
/root/anaconda3/envs/embedding_test/bin/python -u "$APP/EnterpriseRAG-Bench/scripts/diag/compare_bge_conan_retrieval_50_r12.py" \
  --questions "$APP/questions.jsonl" \
  --output "$APP/EnterpriseRAG-Bench/outputs/r12_direct_bge_conan_retrieval_50_20260828.json"
