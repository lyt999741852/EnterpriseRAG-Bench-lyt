#!/bin/bash
echo "=== e5 encode speed under current GPU contention ==="
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
export TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1 CUDA_VISIBLE_DEVICES=2
python3 << 'EOF'
import time
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("/data06/embedding-models/multilingual-e5-large",
                            device="cuda", local_files_only=True)
texts = ["passage: batch item number %d with realistic enterprise text length words here " % i for i in range(256)]

model.encode(texts[:32], batch_size=32, normalize_embeddings=True, show_progress_bar=False)

for trial in range(5):
    t0 = time.time()
    model.encode(texts, batch_size=128, normalize_embeddings=True, show_progress_bar=False)
    dt = time.time() - t0
    print(f"encode 256 (batch128): {dt:.2f}s -> {256/dt:.1f} items/s", flush=True)
EOF
