set -euo pipefail
APP=/opt/enterprise-rag-bench/app
cd "$APP"
/root/anaconda3/envs/embedding_test/bin/python -m compileall -q src/pipeline.py
/root/anaconda3/envs/embedding_test/bin/python - <<'PY'
from pathlib import Path
import yaml

cfg = yaml.safe_load(Path(
    "configs/eval_semantic30_r4_d2b_e5_secondary_20260825.yaml"
).read_text(encoding="utf-8"))
secondary = cfg["retrieval"]["semantic_secondary_dense"]
assert secondary["enabled"] is True
assert "semantic_secondary_dense" in cfg["retrieval"]["multi_view"]["routes"]["semantic"]
assert cfg["pageindex"]["enabled"] is False
assert cfg["pipeline"]["question_ids"]
print("D2B_CONFIG_VALID")
PY
