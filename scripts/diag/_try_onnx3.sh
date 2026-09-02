#!/bin/bash
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
echo "=== available onnxruntime versions on aliyun mirror ==="
timeout 60 pip index versions onnxruntime 2>&1 | tail -3
echo "=== try specific version ==="
timeout 120 pip install onnxruntime==1.18.1 2>&1 | tail -3
/root/anaconda3/envs/embedding_test/bin/python -c "import onnxruntime; print('onnxruntime OK', onnxruntime.__version__)" 2>&1 | tail -1
