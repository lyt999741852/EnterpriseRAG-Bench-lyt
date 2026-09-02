#!/usr/bin/env bash
set -euo pipefail

# Reuse the reviewed O4.P3.4 isolated implementation, changing only run/module
# names. The base script is already uploaded with the pushed P3.4 task.
APP=/opt/enterprise-rag-bench/app
BASE="$APP/scripts/remote/_run_o4p34_deterministic_conflict_smoke4_20260831.sh"
TMP="$APP/scripts/remote/.run_o4p34_conflict_ab50_20260831.sh"
if [ ! -f "$BASE" ]; then
  echo "missing base O4.P3.4 runner: $BASE" >&2
  exit 1
fi
trap 'rm -f "$TMP"' EXIT
sed \
  -e 's/pageindex_o4p34_deterministic_conflict_smoke4_r1_20260831/pageindex_o4p34_conflict_ab50_20260831/g' \
  -e 's/pipeline_o4p34_deterministic_conflict_smoke4_r1/pipeline_o4p34_conflict_ab50/g' \
  -e 's/generator_o4p34_deterministic_conflict_smoke4_r1/generator_o4p34_conflict_ab50/g' \
  -e 's/QUESTION_PARALLELISM=2/QUESTION_PARALLELISM=4/g' \
  "$BASE" > "$TMP"
bash "$TMP"
