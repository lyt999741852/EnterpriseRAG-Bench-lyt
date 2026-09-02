set -u
APP=/opt/enterprise-rag-bench/app
RUN=semantic30_r4_d1_document_first_20260821
DIR="$APP/outputs/$RUN"
echo '--- PROCESS ---'
if [ -f "$DIR/run.pid" ]; then
  pid=$(cat "$DIR/run.pid")
  echo "PIPELINE_PID=$pid"
  ps -p "$pid" -o pid=,stat=,etime=,%cpu=,%mem=,cmd= || true
fi
pgrep -af "src.pipeline.*$RUN|metrics_based_eval.*$RUN" || true
echo '--- FILES ---'
find "$DIR" -maxdepth 1 -type f -printf '%f %s bytes %TY-%Tm-%Td %TH:%TM:%TS\n' 2>/dev/null | sort
echo '--- PIPELINE LOG ---'
tail -n 30 "$DIR/pipeline.log" 2>/dev/null || true
echo '--- SCORE LOG ---'
tail -n 20 "$DIR/score.log" 2>/dev/null || true
echo '--- RESULTS ---'
if [ -f "$DIR/answers.jsonl" ]; then
  echo "answers_lines=$(wc -l < "$DIR/answers.jsonl")"
fi
python - "$DIR/results.json" <<'PY'
import json, sys
from pathlib import Path
p=Path(sys.argv[1])
if not p.exists():
    print('results.json missing')
else:
    d=json.loads(p.read_text(encoding='utf-8'))
    print(json.dumps(d.get('aggregate_stats', {}), ensure_ascii=False, indent=2))
PY
