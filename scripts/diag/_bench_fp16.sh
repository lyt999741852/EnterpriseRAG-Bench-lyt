#!/bin/bash
cd /opt/enterprise-rag-bench/app || exit 1
echo "=== e5 fp16 vs fp32 speed (real long chunks) ==="
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
export TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1 CUDA_VISIBLE_DEVICES=3
python3 << 'EOF'
import json, time
import torch
from sentence_transformers import SentenceTransformer

chunks = []
with open(".index_cache/full_es_e5/chunks.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        chunks.append(d["text"])
        if len(chunks) >= 128:
            break
texts = ["passage: " + t for t in chunks]

# fp32 baseline
model = SentenceTransformer("/data06/embedding-models/multilingual-e5-large",
                            device="cuda", local_files_only=True)
model.encode(texts[:32], normalize_embeddings=True, show_progress_bar=False)
t0 = time.time()
model.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
dt = time.time() - t0
print(f"fp32: {dt:.2f}s -> {128/dt:.1f} items/s", flush=True)

# fp16
model = model.half()
t0 = time.time()
model.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
dt = time.time() - t0
print(f"fp16: {dt:.2f}s -> {128/dt:.1f} items/s", flush=True)
EOF
