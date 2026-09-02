#!/usr/bin/env bash
set -eo pipefail
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
export TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1
echo E5_AUDIT_START
exec python -u /tmp/audit_e5_chunks.py \
  --chunks /opt/enterprise-rag-bench/app/.index_cache/full_es_qwen3_emb_v3_conan448/chunks.jsonl \
  --model /data06/embedding-models/multilingual-e5-large \
  --max-tokens 512 \
  --safety-limit 480 \
  --recommended-size 384 \
  --recommended-overlap 64 \
  --strict
