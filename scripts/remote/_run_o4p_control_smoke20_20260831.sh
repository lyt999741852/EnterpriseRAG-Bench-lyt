#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
RUN=pageindex_o4p_control_smoke20_20260831
cd "$APP"
mkdir -p "outputs/$RUN"
if [ -f "outputs/$RUN/run.pid" ] && kill -0 "$(cat "outputs/$RUN/run.pid")" 2>/dev/null; then
  echo "ALREADY_RUNNING PID=$(cat "outputs/$RUN/run.pid")"
  exit 0
fi
: "${DPV4_API_KEY:?DPV4_API_KEY is required}"
: "${EMBEDDING_API_KEY:?EMBEDDING_API_KEY is required}"

CONTROL_CFG=configs/eval_pageindex_o4p_control_smoke20_20260831.yaml
/root/anaconda3/envs/embedding_test/bin/python - "$CONTROL_CFG" <<'PY'
from pathlib import Path
import sys
import yaml

source = Path("configs/eval_pageindex_o4p_soft_pool_smoke20_20260831.yaml")
target = Path(sys.argv[1])
cfg = yaml.safe_load(source.read_text(encoding="utf-8"))
cfg["pipeline"]["name"] = "pageindex_o4p_control_smoke20_20260831"
cfg["pageindex"]["cache_dir"] = ".pageindex_cache/o4p_control_smoke20_20260831"
cfg["retrieval"]["document_soft_pool"]["enabled"] = False
target.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
PY

export TRANSFORMERS_OFFLINE=1
export QUESTION_PARALLELISM=4
nohup /root/anaconda3/envs/embedding_test/bin/python -u -m src.pipeline \
  "$CONTROL_CFG" \
  > "outputs/$RUN/pipeline.log" 2>&1 < /dev/null &
echo $! > "outputs/$RUN/run.pid"
echo "PID=$(cat "outputs/$RUN/run.pid")"
sleep 2
tail -n 25 "outputs/$RUN/pipeline.log" || true
