#!/bin/bash
echo "=== jina pooling config ==="
cat /data06/jina-embeddings-v3/config_sentence_transformers.json 2>/dev/null
echo "--- modules.json ---"
cat /data06/jina-embeddings-v3/modules.json 2>/dev/null
echo "--- 1_Pooling config ---"
cat /data06/jina-embeddings-v3/1_Pooling/config.json 2>/dev/null
echo "=== kill stale jinaai download ==="
pkill -f 'xlm-roberta-flash' 2>/dev/null
sleep 1
echo "=== pip install onnxruntime-gpu (test pypi reachability) ==="
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
timeout 150 pip install onnxruntime-gpu 2>&1 | tail -5
/root/anaconda3/envs/embedding_test/bin/python -c "import onnxruntime; print('onnxruntime OK', onnxruntime.__version__)" 2>&1 | tail -1
