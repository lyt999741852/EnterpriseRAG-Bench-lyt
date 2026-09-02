#!/bin/bash
echo "=== download jinaai remote code via hf-mirror ==="
export HF_ENDPOINT=https://hf-mirror.com
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
python3 << 'EOF'
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
from huggingface_hub import snapshot_download
try:
    path = snapshot_download("jinaai/xlm-roberta-flash-implementation")
    print("downloaded:", path)
    for root, dirs, files in os.walk(path):
        for f in files[:20]:
            print(" ", os.path.join(root, f))
except Exception as e:
    print("DOWNLOAD FAIL:", type(e).__name__, str(e)[:300])
EOF
