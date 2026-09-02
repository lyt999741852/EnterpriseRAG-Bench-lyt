#!/bin/bash
# Restart new-library build (resume: chunking done, embedding/ES phase)
cd /opt/enterprise-rag-bench/app || exit 1
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
export TRANSFORMERS_OFFLINE=1 LARK_API_KEY=sentosa-qwen3-embedding CUDA_VISIBLE_DEVICES=2
export EMBEDDING_API_KEY=123456
nohup python -u -m src.build_es_index configs/full_es_qwen3_emb.yaml \
  > outputs/build_qwen3_emb_20260805.log 2>&1 &
echo "started pid $!"
