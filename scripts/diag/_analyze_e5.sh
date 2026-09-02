#!/bin/bash
echo "=== multilingual-e5-large config ==="
cat /data06/embedding-models/multilingual-e5-large/config.json 2>/dev/null | python3 -c "
import json, sys
d = json.load(sys.stdin)
for k in ('model_type','architectures','hidden_size','num_hidden_layers','max_position_embeddings','vocab_size','num_attention_heads'):
    print(f'  {k}: {d.get(k)}')
"
cat /data06/embedding-models/multilingual-e5-large/1_Pooling/config.json 2>/dev/null | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('  pooling:', {k: v for k, v in d.items() if 'pooling' in k})
"
echo "=== e5 tokenizer stats on existing chunks (max tokens < 512?) ==="
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
export TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1
python3 << 'EOF'
import json
from transformers import AutoTokenizer

tok = AutoTokenizer.from_pretrained("/data06/embedding-models/multilingual-e5-large", local_files_only=True)
print("tokenizer type:", type(tok).__name__)

max_t = 0
n = 0
over = 0
batch = []
with open("/opt/enterprise-rag-bench/app/.index_cache/full_es_qwen3_emb/chunks.jsonl", encoding="utf-8") as f:
    for line in f:
        batch.append(json.loads(line))
        if len(batch) >= 4096:
            enc = tok([r["text"] for r in batch], add_special_tokens=False, verbose=False)
            for ids in enc["input_ids"]:
                t = len(ids)
                max_t = max(max_t, t)
                if t > 480:
                    over += 1
                n += 1
            batch = []
    if batch:
        enc = tok([r["text"] for r in batch], add_special_tokens=False, verbose=False)
        for ids in enc["input_ids"]:
            t = len(ids)
            max_t = max(max_t, t)
            if t > 480:
                over += 1
            n += 1
print(f"chunks: {n}, e5-tokenizer max: {max_t}, >480: {over}")
EOF
