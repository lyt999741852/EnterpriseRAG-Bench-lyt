#!/bin/bash
# Start v3 Conan448 ES index build on the server (embedding API + ES 7.17).
# Precondition: chunks cache synced to .index_cache/full_es_qwen3_emb_v3_conan448/
#   (chunks.jsonl + manifest.sqlite3 + conan_tokenizer/).
# Resume-safe: deterministic chunk_id + _mget skip + es_build_progress.json.
cd /opt/enterprise-rag-bench/app || exit 1
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
export EMBEDDING_API_KEY=123456
nohup python -u -m src.build_es_index configs/full_es_qwen3_emb_v3_conan448.yaml \
  > outputs/build_v3_conan448_20260812.log 2>&1 &
echo "started pid $!"
