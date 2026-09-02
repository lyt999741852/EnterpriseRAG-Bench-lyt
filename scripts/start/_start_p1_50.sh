#!/bin/bash
# P1 partial-open 50-question stratified run (single variable vs V5.2)
cd /opt/enterprise-rag-bench/app || exit 1
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
export TRANSFORMERS_OFFLINE=1 LARK_API_KEY=sentosa-qwen3-embedding CUDA_VISIBLE_DEVICES=2
nohup python -m src.pipeline configs/eval_pageindex_balanced50_p1.yaml \
  > outputs/p1_50_run_20260804.log 2>&1 &
echo "started pid $!"
