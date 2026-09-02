#!/bin/bash
echo "=== try install onnxruntime (CPU) ==="
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
timeout 150 pip install onnxruntime 2>&1 | tail -3
/root/anaconda3/envs/embedding_test/bin/python -c "import onnxruntime; print('onnxruntime OK', onnxruntime.__version__)" 2>&1 | tail -1
echo "=== try onnxruntime-gpu from pypi directly ==="
timeout 150 pip install onnxruntime-gpu -i https://pypi.org/simple/ 2>&1 | tail -3
/root/anaconda3/envs/embedding_test/bin/python -c "import onnxruntime; print('onnxruntime-gpu OK', onnxruntime.__version__)" 2>&1 | tail -1
echo "=== ONNX model info ==="
/root/anaconda3/envs/embedding_test/bin/python - << 'EOF' 2>&1 | tail -20
import onnxruntime as ort
sess = ort.InferenceSession("/data06/jina-embeddings-v3/onnx/model.onnx", providers=["CPUExecutionProvider"])
for i in sess.get_inputs():
    print("input:", i.name, i.shape, i.type)
for o in sess.get_outputs():
    print("output:", o.name, o.shape, o.type)
EOF
