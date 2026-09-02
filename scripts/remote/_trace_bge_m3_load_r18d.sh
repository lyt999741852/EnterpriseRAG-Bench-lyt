set -u
python3 - <<'PY'
import traceback
from transformers import AutoTokenizer, AutoModel
base='/data01/.cache/home/hub/models--BAAI--bge-m3/snapshots/5617a9f61b028005a4858fdac845db406aefb181'
try:
 tok=AutoTokenizer.from_pretrained(base,local_files_only=True)
 print('tokenizer_ok')
 model=AutoModel.from_pretrained(base,local_files_only=True)
 print('model_ok')
except Exception:
 traceback.print_exc()
PY
