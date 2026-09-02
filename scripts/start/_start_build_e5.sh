#!/bin/bash
# Copy chunk artifacts to new index dir, then build e5 vector library
cd /opt/enterprise-rag-bench/app || exit 1
mkdir -p .index_cache/full_es_e5
cp .index_cache/full_es_qwen3_emb/chunks.jsonl .index_cache/full_es_e5/chunks.jsonl
cp .index_cache/full_es_qwen3_emb/manifest.sqlite3 .index_cache/full_es_e5/manifest.sqlite3
cp .index_cache/full_es_qwen3_emb/failed_files.jsonl .index_cache/full_es_e5/failed_files.jsonl 2>/dev/null
ls -la .index_cache/full_es_e5/
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
export TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1 LARK_API_KEY=sentosa-qwen3-embedding CUDA_VISIBLE_DEVICES=3
nohup python -u -m src.build_es_index configs/full_es_e5.yaml \
  > outputs/build_e5_20260806.log 2>&1 &
echo "build started pid $!"
