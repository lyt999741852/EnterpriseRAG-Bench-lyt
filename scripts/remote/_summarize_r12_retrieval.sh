set -euo pipefail
python - <<'PY'
import json
from collections import Counter
p='/opt/enterprise-rag-bench/app/EnterpriseRAG-Bench/outputs/r12_direct_bge_conan_retrieval_50_20260828.json'
d=json.load(open(p,encoding='utf-8'))
rows=d['rows']
for k in (30,120,240,1000):
    def hit(r, name):
        rank=r[name+'_rank']
        return rank is not None and rank<=k
    both=sum(hit(r,'bge') and hit(r,'conan') for r in rows)
    b=sum(hit(r,'bge') for r in rows); c=sum(hit(r,'conan') for r in rows)
    print(f'k={k} bge={b} conan={c} both={both} union={b+c-both} bge_only={b-both} conan_only={c-both}')
print('conan_better',sum((r['conan_rank'] is not None and (r['bge_rank'] is None or r['conan_rank']<r['bge_rank'])) for r in rows))
print('bge_better',sum((r['bge_rank'] is not None and (r['conan_rank'] is None or r['bge_rank']<r['conan_rank'])) for r in rows))
print('same_rank',sum(r['bge_rank']==r['conan_rank'] for r in rows))
print('types',Counter(r['question_type'] for r in rows))
PY
