#!/bin/bash
echo "=== jina-v3 config ==="
cat /data06/jina-embeddings-v3/config.json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print({k:v for k,v in d.items() if k in ('auto_map','model_type','architectures','max_position_embeddings','hidden_size')})" 2>/dev/null || head -20 /data06/jina-embeddings-v3/config.json
echo "=== onnx dir ==="
find /data06/jina-embeddings-v3/onnx -type f 2>/dev/null | head -10
echo "=== onnxruntime available? ==="
/root/anaconda3/envs/embedding_test/bin/python -c "import onnxruntime; print('onnxruntime', onnxruntime.__version__)" 2>&1 | tail -1
echo "=== tokenizer files ==="
ls /data06/jina-embeddings-v3/*.json /data06/jina-embeddings-v3/*.model /data06/jina-embeddings-v3/*.txt 2>/dev/null
echo "=== try standard-load without remote code ==="
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
export TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1
python3 << 'EOF'
import json, os
cfg_path = "/data06/jina-embeddings-v3/config.json"
cfg = json.load(open(cfg_path))
print("auto_map present:", "auto_map" in cfg)
if "auto_map" in cfg:
    print("auto_map:", cfg["auto_map"])
    import copy
    cfg2 = copy.deepcopy(cfg)
    cfg2.pop("auto_map", None)
    json.dump(cfg2, open("/tmp/jina_no_autoload.json", "w"))
    from transformers import AutoConfig
    try:
        c = AutoConfig.from_pretrained("/tmp/jina_no_autoload.json")
        print("config ok, model_type:", c.model_type)
    except Exception as e:
        print("config fail:", str(e)[:200])
EOF
