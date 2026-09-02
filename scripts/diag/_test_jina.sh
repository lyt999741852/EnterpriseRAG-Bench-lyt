#!/bin/bash
echo "=== jina-embeddings-v3 local load test ==="
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
python3 << 'EOF'
import time
from sentence_transformers import SentenceTransformer

t0 = time.time()
model = SentenceTransformer(
    "/data06/jina-embeddings-v3",
    device="cuda:2",
    trust_remote_code=True,
)
print("load: %.1fs" % (time.time() - t0))

texts = ["batch item number %d with realistic enterprise text length words here" % i for i in range(128)]
t0 = time.time()
vecs = model.encode(texts, batch_size=128, normalize_embeddings=True, show_progress_bar=False)
dt = time.time() - t0
print("batch 128: %.2fs (%.1f items/s) dim=%s" % (dt, 128 / dt, vecs.shape[1]))

# long text (9k chars)
long_text = "long text test " * 2300
t0 = time.time()
v = model.encode([long_text], normalize_embeddings=True, show_progress_bar=False)
print("long 9k-char: %.2fs ok=%s" % (time.time() - t0, v.shape[1] > 0))
EOF
