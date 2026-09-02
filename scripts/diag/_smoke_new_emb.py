"""Server-side end-to-end smoke: hierarchical chunker + new embedding API on
a small corpus sample (build a 2-source index into a temp ES index)."""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import paramiko

PASSWORD = "XAznv@(2018)"
HOST = "10.72.100.29"
REMOTE_ROOT = "/opt/enterprise-rag-bench/app"

REMOTE_SCRIPT = r'''
import json
import os
import sys
import time

sys.path.insert(0, "/opt/enterprise-rag-bench/app")
os.environ.setdefault("EMBEDDING_API_KEY", "123456")

from src.indexer import Indexer, IndexerConfig, _chunk_text_hierarchical, _count_tokens
from src.embedder import EmbedderConfig

# 1) real tokenizer chunking stats on a sample doc
sample = open("/opt/enterprise-rag-bench/app/corpus/all_documents/confluence/company-handbook/00_overview/dsid_9692a02fcc544153bb7f721a05199d27__first-year-success-and-benefits-roadmap-2025.txt", encoding="utf-8", errors="replace").read()[:20000]
t0 = time.time()
chunks = _chunk_text_hierarchical(sample, 384, 64)
print("sample chunks:", len(chunks), "in %.2fs" % (time.time() - t0))
for c in chunks[:4]:
    print("  tokens=%d chars=%d start=%d end=%d" % (_count_tokens(c["text"]), len(c["text"]), c["start"], c["end"]))
max_tok = max(_count_tokens(c["text"]) for c in chunks)
print("  max chunk tokens:", max_tok, "(limit 512)")

# 2) embedder sanity via API
from src.embedder import create_embedder
emb = create_embedder(EmbedderConfig(
    provider="openai_compatible",
    model_name="embedding",
    api_base="http://10.72.55.209:7993/v1",
    api_key_env="EMBEDDING_API_KEY",
    batch_size=8,
    dimension=1792,
))
print("embedder dim:", emb.dimension)
vecs = emb.encode([c["text"] for c in chunks[:3]])
print("encoded shape:", vecs.shape, "finite:", bool((vecs == vecs).all() and (vecs != float("inf")).all()))
'''

def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=15)
    sftp = client.open_sftp()
    with sftp.open(f"{REMOTE_ROOT}/_smoke_new_emb.py", "w") as f:
        f.write(REMOTE_SCRIPT)
    sftp.close()
    try:
        _, stdout, stderr = client.exec_command(
            f"cd {REMOTE_ROOT} && source /root/anaconda3/etc/profile.d/conda.sh && conda activate embedding_test && python _smoke_new_emb.py",
            timeout=600,
        )
        out = stdout.read().decode("utf-8", "replace").strip()
        err = stderr.read().decode("utf-8", "replace").strip()
        if out:
            print(out)
        if err:
            print(f"[stderr] {err[-2500:]}")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
