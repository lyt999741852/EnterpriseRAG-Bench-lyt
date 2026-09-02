cd /opt/enterprise-rag-bench/app
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
export TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false
python - <<'PY'
import json, os, time
from pathlib import Path
import torch
from sentence_transformers import SentenceTransformer
n=int(os.environ.get('THREADS','16'))
torch.set_num_threads(n)
torch.set_num_interop_threads(1)
texts=[]
with Path('.index_cache/full_es_bge_large_en_v1_448_32/chunks.jsonl').open(encoding='utf-8') as f:
    for _ in range(128):
        texts.append(json.loads(f.readline())['text'])
m=SentenceTransformer('/data06/embedding-models/bge-large-en-v1.5',device='cpu',local_files_only=True)
t=time.time()
m.encode(texts,batch_size=128,normalize_embeddings=True,show_progress_bar=False)
dt=time.time()-t
print('THREADS',n,'SECONDS',round(dt,2),'RATE',round(128/dt,2),flush=True)
PY
