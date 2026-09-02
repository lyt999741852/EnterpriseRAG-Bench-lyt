cd /opt/enterprise-rag-bench/app
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
export TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1
set -u
python - <<'PY'
import json, urllib.request, numpy as np
from sentence_transformers import SentenceTransformer
body=json.dumps({'size':100,'query':{'match_all':{}},'_source':['text','embedding','doc_id']}).encode()
req=urllib.request.Request('http://127.0.0.1:9200/enterprise-rag-bge-large-r14-candidates50-k40/_search',data=body,method='POST',headers={'Content-Type':'application/json'})
hits=json.loads(urllib.request.urlopen(req,timeout=300).read().decode())['hits']['hits']
r=[h['_source'] for h in hits]; texts=[x.get('text','') for x in r]; vec=np.asarray([x['embedding'] for x in r],dtype=np.float32)
m=SentenceTransformer('/data06/embedding-models/bge-large-en-v1.5',device='cpu',local_files_only=True); q=np.asarray(m.encode('What is the status of the project?',normalize_embeddings=True),dtype=np.float32); s=vec@q
print('N',len(r),'DIM',vec.shape,'finite',np.isfinite(vec).all(),np.isfinite(q).all(),'score',float(s.min()),float(s.max()),float(s.std()),'argmax',int(np.argmax(s)))
PY
