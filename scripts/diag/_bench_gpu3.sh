#!/bin/bash
cd /opt/enterprise-rag-bench/app || exit 1
echo "=== e5 speed on GPU 3 (real long chunks) ==="
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
export TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1 CUDA_VISIBLE_DEVICES=3
python3 << 'EOF'
import json, time
from sentence_transformers import SentenceTransformer

chunks = []
with open(".index_cache/full_es_e5/chunks.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        chunks.append(d["text"])
        if len(chunks) >= 128:
            break

model = SentenceTransformer("/data06/embedding-models/multilingual-e5-large",
                            device="cuda", local_files_only=True)
texts = ["passage: " + t for t in chunks]
model.encode(texts[:32], batch_size=32, normalize_embeddings=True, show_progress_bar=False)
for trial in range(3):
    t0 = time.time()
    model.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
    dt = time.time() - t0
    print(f"GPU3 batch64: {dt:.2f}s -> {128/dt:.1f} items/s", flush=True)
EOF
nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv | head -6
