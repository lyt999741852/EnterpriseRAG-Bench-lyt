#!/usr/bin/env bash
set -euo pipefail

DIR=/opt/enterprise-rag-bench/app/outputs/semantic30_r4_d2a_wide_candidates_20260825
TARGET="$DIR/run_meta.serial_before_parallel.json"
test -f "$TARGET"
rm -f -- "$TARGET"
echo "removed=$TARGET"
echo "current_answers=$(wc -l < "$DIR/answers.jsonl")"
echo "current_pid=$(cat "$DIR/run.pid")"
