#!/bin/bash
# Restart v3 Conan448 ES build with the current config (resume-safe).
pkill -f 'src.build_es_index' 2>/dev/null
sleep 3
cd /opt/enterprise-rag-bench/app || exit 1
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
export EMBEDDING_API_KEY=123456
nohup python -u -m src.build_es_index configs/full_es_qwen3_emb_v3_conan448.yaml \
  >> outputs/build_v3_conan448_20260812.log 2>&1 &
echo "restarted pid $!"
