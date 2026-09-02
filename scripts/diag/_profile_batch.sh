#!/bin/bash
cd /opt/enterprise-rag-bench/app || exit 1
echo "=== profile one index_chunks batch (256 real chunks) ==="
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
export TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1 CUDA_VISIBLE_DEVICES=2
python3 << 'EOF'
import json, time
import numpy as np

from src.indexer import Chunk
from src.embedder import EmbedderConfig, create_embedder
from src.elasticsearch_backend import ElasticsearchBackend, ElasticsearchConfig

# load first 256 real chunks
chunks = []
with open("/opt/enterprise-rag-bench/app/.index_cache/full_es_e5/chunks.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        chunks.append(Chunk(**d))
        if len(chunks) >= 256:
            break

emb = create_embedder(EmbedderConfig(
    provider="sentence_transformers",
    model_name="/data06/embedding-models/multilingual-e5-large",
    device="cuda",
    batch_size=128,
    dimension=1024,
    document_prefix="passage: ",
))
print("embedder ready")

# warmup
emb.encode([c.text for c in chunks[:16]], show_progress=False)

# step 1: existing ids (mget)
backend = ElasticsearchBackend(ElasticsearchConfig(index_name="enterprise-rag-e5-large-v1"))
t0 = time.time()
present = backend._existing_ids([c.chunk_id for c in chunks])
t1 = time.time()
print(f"mget 256: {t1-t0:.3f}s, present={len(present)}")

# step 2: encode once (256)
t0 = time.time()
vecs = emb.encode([c.text for c in chunks], show_progress=False).astype(np.float32)
t1 = time.time()
print(f"encode 256 once: {t1-t0:.3f}s ({256/(t1-t0):.0f}/s)")

# step 3: isfinite
t0 = time.time()
_ = np.isfinite(vecs).all()
t1 = time.time()
print(f"isfinite: {t1-t0:.4f}s")

# step 4: JSON serialize (tolist + dumps)
t0 = time.time()
operations = []
for chunk, vector in zip(chunks, vecs):
    operations.append(json.dumps({"index": {"_index": "enterprise-rag-e5-large-v1", "_id": chunk.chunk_id}}, separators=(",", ":")))
    operations.append(json.dumps({
        "chunk_id": chunk.chunk_id, "doc_id": chunk.doc_id, "source_type": chunk.source_type,
        "text": chunk.text, "chunk_index": 0, "char_start": chunk.char_start, "char_end": chunk.char_end,
        "embedding_model": "e5", "embedding": vector.tolist(),
    }, ensure_ascii=False, separators=(",", ":")))
t1 = time.time()
print(f"json serialize 256 (1024d): {t1-t0:.3f}s, payload={sum(len(o) for o in operations)//1024}KB")

# step 5: bulk
t0 = time.time()
resp = backend._request("POST", "/_bulk", "\n".join(operations) + "\n", content_type="application/x-ndjson")
t1 = time.time()
print(f"bulk 256: {t1-t0:.3f}s")
EOF
