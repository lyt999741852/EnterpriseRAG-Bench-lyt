cd /opt/enterprise-rag-bench/app
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
export TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1
python - <<'PY'
from src.indexer import Indexer, IndexerConfig
from src.embedder import EmbedderConfig

cfg = IndexerConfig(
    corpus_dir='/opt/enterprise-rag-bench/app/corpus/all_documents',
    chunk_size=448,
    chunk_overlap=32,
    embedder=EmbedderConfig(provider='sentence_transformers', model_name='/data06/embedding-models/bge-large-en-v1.5', device='cpu', batch_size=128, dimension=1024),
    overwrite=False,
    enable_faiss=False,
    enable_bm25=False,
    cache_dir='/opt/enterprise-rag-bench/app/.index_cache/full_es_bge_large_en_v1_448_32',
    chunker_version='fixed-v2',
    chunking_method='fixed',
    manifest_enabled=True,
)
print(Indexer(cfg).build())
PY
