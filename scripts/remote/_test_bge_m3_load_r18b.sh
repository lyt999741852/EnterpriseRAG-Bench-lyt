set -u
base=/data01/.cache/home/hub/models--BAAI--bge-m3
echo '=== SNAPSHOT LINKS ==='
ls -la "$base/snapshots" 2>/dev/null || true
ref=$(cat "$base/refs/main" 2>/dev/null || true)
echo "ref=$ref"
if [ -n "$ref" ]; then
  ls -la "$base/snapshots/$ref" 2>/dev/null | head -60 || true
  echo 'config:'
  for f in "$base/snapshots/$ref/config.json" "$base/snapshots/$ref/sentence_bert_config.json"; do [ -f "$f" ] && { echo "[$f]"; grep -E 'hidden_size|model_type|architectures|pooling|max_position_embeddings' "$f" | head -30; }; done
fi
echo '=== TRANSFORMERS CPU SMOKE ==='
python3 - <<'PY'
import os,sys,time,torch
from transformers import AutoConfig, AutoTokenizer, AutoModel
base='/data01/.cache/home/hub/models--BAAI--bge-m3'
ref=open(base+'/refs/main').read().strip()
path=base+'/snapshots/'+ref
print('path',path)
try:
 c=AutoConfig.from_pretrained(path,local_files_only=True)
 print('config_ok',c.model_type,getattr(c,'hidden_size',None),getattr(c,'vocab_size',None))
 tok=AutoTokenizer.from_pretrained(path,local_files_only=True)
 model=AutoModel.from_pretrained(path,local_files_only=True,torch_dtype=torch.float32)
 model.eval()
 batch=tok(['enterprise retrieval test'],return_tensors='pt',padding=True,truncation=True)
 with torch.no_grad(): out=model(**batch).last_hidden_state
 emb=out[:,0,:]
 print('encode_ok',tuple(out.shape),'pooled',tuple(emb.shape),'norm',float(emb.norm()))
except Exception as e:
 print('load_failed',type(e).__name__,str(e)[:500])
 sys.exit(2)
PY
