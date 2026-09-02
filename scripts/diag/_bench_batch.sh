#!/bin/bash
cd /opt/enterprise-rag-bench/app || exit 1
echo "=== e5 encode speed on REAL long chunks, varying batch ==="
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
export TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1 CUDA_VISIBLE_DEVICES=2
python3 << 'EOF'
import json, time
from sentence_transformers import SentenceTransformer

chunks = []
with open(".index_cache/full_es_e5/chunks.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        chunks.append(d["text"])
        if len(chunks) >= 256:
            break
lens = [len(t) for t in chunks]
print(f"real chunk lens: min={min(lens)} max={max(lens)} avg={sum(lens)//len(lens)}")

model = SentenceTransformer("/data06/embedding-models/multilingual-e5-large",
                            device="cuda", local_files_only=True)

for bs in [128, 64, 32, 16]:
    texts = ["passage: " + t for t in chunks]
    model.encode(texts[:bs], batch_size=bs, normalize_embeddings=True, show_progress_bar=False)  # warmup
    t0 = time.time()
    model.encode(texts, batch_size=bs, normalize_embeddings=True, show_progress_bar=False)
    dt = time.time() - t0
    print(f"batch {bs}: {dt:.2f}s -> {256/dt:.1f} items/s", flush=True)
EOF
