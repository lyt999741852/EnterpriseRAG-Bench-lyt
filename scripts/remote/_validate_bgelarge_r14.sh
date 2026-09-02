cd /opt/enterprise-rag-bench/app
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
export TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1
set -u
python - <<'PY'
from sentence_transformers import SentenceTransformer
path='/data06/embedding-models/bge-large-en-v1.5'
model=SentenceTransformer(path, device='cpu', local_files_only=True)
vec=model.encode('test retrieval question', normalize_embeddings=True)
print('MODEL_OK', path)
print('DIM', len(vec))
print('NORM', float((vec**2).sum() ** 0.5))
PY
