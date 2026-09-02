#!/bin/bash
# Check build environment deps on the server (embedding_test conda env).
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
pip show transformers langchain-text-splitters faiss-cpu 2>/dev/null | grep -E '^(Name|Version)'
