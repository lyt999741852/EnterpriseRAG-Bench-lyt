RUN=/opt/enterprise-rag-bench/app/outputs/pageindex_full500_bge_dpv4_20260831
/root/anaconda3/bin/python - "$RUN/results.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
print(json.dumps(d.get('aggregate_stats'),ensure_ascii=False,indent=2))
print(json.dumps(d.get('question_type_stats'),ensure_ascii=False,indent=2))
PY
