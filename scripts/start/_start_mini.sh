#!/bin/bash
# Mini build: 5000 chunks end-to-end verification (chunker + new embedding API + ES)
cd /opt/enterprise-rag-bench/app || exit 1
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
export TRANSFORMERS_OFFLINE=1 LARK_API_KEY=sentosa-qwen3-embedding CUDA_VISIBLE_DEVICES=2
export EMBEDDING_API_KEY=123456
nohup python -u -m src.build_es_index configs/mini_qwen3_emb.yaml \
  > outputs/build_mini_qwen3_emb.log 2>&1 &
echo "started pid $!"
