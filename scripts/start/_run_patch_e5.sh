#!/bin/bash
# Step 1: patch chunks.jsonl for e5 tokenizer; Step 2: copy chunk artifacts to new index dir
cd /opt/enterprise-rag-bench/app || exit 1
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
export TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1
echo "=== patch chunks for e5 tokenizer ==="
nohup python -u _patch_e5_chunks.py > /tmp/patch_e5.log 2>&1 &
echo "patch started pid $!"
