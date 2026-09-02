"""Server-side verification: does jionglin-embedding tokenizer match the Conan API token counts?

For the first 20 real chunks: count tokens with the local jionglin tokenizer,
then ask the API (single-item requests) and compare with API-reported counts
(400 errors carry the API's own token count).
"""
import json
import os
import urllib.request
from urllib.error import HTTPError

from transformers import AutoTokenizer

API = "http://10.72.55.209:7993/v1/embeddings"
KEY = "123456"
SAMPLE = "/opt/enterprise-rag-bench/app/.index_cache/full_es_qwen3_emb/chunks.jsonl"

tok = AutoTokenizer.from_pretrained("Qwen/Qwen-14B-Chat", local_files_only=True)
print("tokenizer loaded:", type(tok).__name__)

rows = []
with open(SAMPLE, encoding="utf-8") as f:
    for i, line in enumerate(f):
        if i >= 20:
            break
        rows.append(json.loads(line).get("text", ""))

for idx, text in enumerate(rows):
    jt = len(tok.encode(text, add_special_tokens=False))
    body = json.dumps({
        "model": "embedding", "input": [text], "encoding_format": "float",
    }).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {KEY}",
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        print(f"#{idx}: jionglin={jt} api=OK({len(data.get('data', []))} vec)")
    except HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        import re
        m = re.search(r"has (\d+) input tokens", detail)
        api_tokens = int(m.group(1)) if m else "?"
        print(f"#{idx}: jionglin={jt} api={api_tokens} (400)")
