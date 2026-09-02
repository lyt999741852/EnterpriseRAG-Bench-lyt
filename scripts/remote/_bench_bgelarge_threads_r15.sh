cd /opt/enterprise-rag-bench/app
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
export TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false
python - <<'PY'
import json,time
from pathlib import Path
import torch
from sentence_transformers import SentenceTransformer
texts=[]
with Path('.index_cache/full_es_bge_large_en_v1_448_32/chunks.jsonl').open(encoding='utf-8') as f:
    for _ in range(128): texts.append(json.loads(f.readline())['text'])
model=SentenceTransformer('/data06/embedding-models/bge-large-en-v1.5',device='cpu',local_files_only=True)
for n in (8,16,32,48,64):
    torch.set_num_threads(n); torch.set_num_interop_threads(1)
    t=time.time(); model.encode(texts,batch_size=128,normalize_embeddings=True,show_progress_bar=False); dt=time.time()-t
    print('THREADS',n,'SECONDS',round(dt,2),'RATE',round(128/dt,2),flush=True)
PY
