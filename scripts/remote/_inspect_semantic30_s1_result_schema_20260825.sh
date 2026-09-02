set -euo pipefail

RUN=/opt/enterprise-rag-bench/app/outputs/semantic30_r4_s1_lexical_anchor_20260820
/root/anaconda3/envs/embedding_test/bin/python - "$RUN/results.json" <<'PY'
import json, sys
from pathlib import Path
data=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
print("TOP_LEVEL", sorted(data))
for key, value in data.items():
    if isinstance(value, list):
        print("LIST", key, len(value), "FIRST", json.dumps(value[0], ensure_ascii=False)[:2000] if value else "")
    elif isinstance(value, dict):
        print("DICT", key, sorted(value)[:30])
PY
