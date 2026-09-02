"""Find embedding API max input length + batch 512 + transformers tokenizer check."""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import paramiko

PASSWORD = "XAznv@(2018)"
HOST = "10.72.100.29"

REMOTE_SCRIPT = r'''
import json
import time
import urllib.request
import urllib.error

URL = "http://10.72.55.209:7993/v1/embeddings"
KEY = "123456"

def call(texts):
    body = json.dumps({"model": "embedding", "input": texts}).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())

# batch 512
t0 = time.time()
r = call(["batch item number %d with realistic enterprise text length words" % i for i in range(512)])
dt = time.time() - t0
print("batch 512: %.2fs (%.1f items/s)" % (dt, 512 / dt))

# length limit binary search: 512..2048 tokens (approx chars = tokens*4.2)
def probe(n_tokens):
    text = ("word " * n_tokens).strip()
    try:
        t0 = time.time()
        r = call([text])
        return True, r.get("usage", {}).get("total_tokens")
    except urllib.error.HTTPError as e:
        return False, e.code

for n in [512, 768, 1024, 1280, 1536, 1792, 2048]:
    ok, info = probe(n)
    print(f"approx {n} tokens: {'OK' if ok else 'FAIL'} {info}")

# transformers tokenizer available in embedding_test?
import subprocess
r = subprocess.run([
    "/root/anaconda3/envs/embedding_test/bin/python", "-c",
    "from transformers import AutoTokenizer; t = AutoTokenizer.from_pretrained('/opt/enterprise-rag-bench/model_cache/hub/models--BAAI--bge-small-en-v1.5/snapshots/5c38ec7c405ec4b44b94cc5a9bb96e735b38267a'); print('tokenizer OK', len(t.encode('hello world example text')))"
], capture_output=True, text=True, timeout=120)
print("transformers tokenizer:", r.stdout.strip() or r.stderr.strip()[-300:])
'''

def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=15)
    sftp = client.open_sftp()
    with sftp.open("/tmp/_probe3.py", "w") as f:
        f.write(REMOTE_SCRIPT)
    sftp.close()
    try:
        _, stdout, stderr = client.exec_command("python3 /tmp/_probe3.py", timeout=900)
        out = stdout.read().decode("utf-8", "replace").strip()
        err = stderr.read().decode("utf-8", "replace").strip()
        if out:
            print(out)
        if err:
            print(f"[stderr] {err[:1500]}")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
