#!/bin/bash
cd /opt/enterprise-rag-bench/app || exit 1
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
nohup python -u _diag_oversized.py > /tmp/diag_os.log 2>&1 &
echo "started pid $!"
