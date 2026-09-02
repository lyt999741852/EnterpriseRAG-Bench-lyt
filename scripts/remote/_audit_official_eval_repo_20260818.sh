#!/usr/bin/env bash
set -u
EVAL=/opt/enterprise-rag-bench/app/EnterpriseRAG-Bench
echo 'EVAL_PATH'
pwd
cd "$EVAL" 2>/dev/null || { echo 'MISSING'; exit 0; }
echo 'GIT_REMOTE'
git remote -v || true
echo 'GIT_HEAD'
git rev-parse HEAD || true
echo 'GIT_STATUS'
git status --short || true
echo 'GIT_BRANCH'
git branch --show-current || true
echo 'EVAL_FILES'
find src -path '*answer_evaluation*' -maxdepth 5 -type f -printf '%p %s bytes\n' 2>/dev/null | sort | head -80
echo 'HELP'
python -m src.scripts.answer_evaluation.metrics_based_eval --help 2>&1 | head -120 || true
