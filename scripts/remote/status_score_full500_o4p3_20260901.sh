RUN=/opt/enterprise-rag-bench/app/outputs/pageindex_full500_bge_dpv4_o4p3_20260901
echo '=== SCORE PROCESS ==='
pgrep -af metrics_based_eval || true
echo '=== RESULT ==='
if [ -f "$RUN/results.json" ]; then ls -lh "$RUN/results.json"; tail -n 25 "$RUN/results.json"; else echo 'results.json not present'; fi
if [ -f "$RUN/results.json" ]; then
  /root/anaconda3/bin/python - "$RUN/results.json" <<'PY'
import json,sys
try:
    d=json.load(open(sys.argv[1],encoding='utf-8'))
    if isinstance(d,list):
        print('scored_rows=',len(d))
    elif isinstance(d,dict):
        print('result_keys=',sorted(d.keys()))
        for key,val in d.items():
            if isinstance(val,list): print('list_field',key,'count=',len(val))
except Exception as exc:
    print('score_parse=',exc)
PY
fi
if [ -f "$RUN/results.json" ]; then
  /root/anaconda3/bin/python - "$RUN/results.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
print('=== AGGREGATE ===')
print(json.dumps(d.get('aggregate_stats'),ensure_ascii=False,indent=2))
print('=== TYPES ===')
print(json.dumps(d.get('question_type_stats'),ensure_ascii=False,indent=2))
PY
fi
