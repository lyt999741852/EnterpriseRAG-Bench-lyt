#!/usr/bin/env bash
set -u
RUN=/opt/enterprise-rag-bench/app/outputs/pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817
echo 'SCORE_LOG'
tail -n 30 "$RUN/score.log" 2>/dev/null || true
echo 'RESULT_AGGREGATE'
python - "$RUN/results.json" <<'PY'
import json
import sys
from pathlib import Path
p = Path(sys.argv[1])
if not p.exists():
    print('results.json missing')
    raise SystemExit(0)
d = json.loads(p.read_text(encoding='utf-8'))
print(json.dumps(d.get('aggregate_stats', {}), ensure_ascii=False, indent=2))
PY
