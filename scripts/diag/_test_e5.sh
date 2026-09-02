#!/bin/bash
echo "=== multilingual-e5-large structure ==="
ls /data06/embedding-models/multilingual-e5-large/ 2>/dev/null | head -10
echo "=== load + benchmark ==="
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
export TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1
python3 << 'EOF'
import time
from sentence_transformers import SentenceTransformer

t0 = time.time()
try:
    model = SentenceTransformer(
        "/data06/embedding-models/multilingual-e5-large",
        device="cuda:2",
        local_files_only=True,
    )
    print("load: %.1fs" % (time.time() - t0))
except Exception as e:
    print("LOAD FAIL:", type(e).__name__, str(e)[:300])
    raise SystemExit(1)

texts = ["passage: batch item number %d with realistic enterprise text length words here" % i for i in range(128)]
t0 = time.time()
vecs = model.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
dt = time.time() - t0
print("batch 64x2: %.2fs (%.1f items/s) dim=%s" % (dt, 128 / dt, vecs.shape[1]))

# bigger batch
texts2 = texts * 4
t0 = time.time()
vecs = model.encode(texts2, batch_size=128, normalize_embeddings=True, show_progress_bar=False)
dt = time.time() - t0
print("batch 128x4: %.2fs (%.1f items/s)" % (dt, 512 / dt))

long_text = "passage: long text test " * 2300
t0 = time.time()
v = model.encode([long_text], normalize_embeddings=True, show_progress_bar=False)
print("long 9k-char: %.2fs ok=%s" % (time.time() - t0, v.shape[1] > 0))
EOF
