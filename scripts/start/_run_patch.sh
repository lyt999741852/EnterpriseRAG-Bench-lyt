#!/bin/bash
cd /opt/enterprise-rag-bench/app || exit 1
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
nohup python -u _patch_chunks.py > /tmp/patch_chunks.log 2>&1 &
echo "started pid $!"
