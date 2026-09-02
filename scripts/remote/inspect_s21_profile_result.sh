cd /opt/enterprise-rag-bench/app
/root/anaconda3/envs/embedding_test/bin/python - <<'PY'
import json
p='outputs/pageindex_full500_bge_dpv4_20260831/s2_1_profile_expansion_20260901.json'
r=json.load(open(p,encoding='utf-8'))
for qid in ['qst_0247']:
    row=next(x for x in r['rows'] if x['question_id']==qid)
    print(json.dumps(row,ensure_ascii=False,indent=2))
PY
