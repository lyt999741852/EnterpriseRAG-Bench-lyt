"""Probe internal embedding API: dimension, batch, tokens, speed."""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import paramiko

PASSWORD = "XAznv@(2018)"
HOST = "10.72.100.29"

REMOTE_SCRIPT = r'''
import json
import time
import urllib.request

URL = "http://10.72.55.209:7993/v1/embeddings"
KEY = "123456"
MODEL = "embedding"

def call(texts):
    body = json.dumps({"model": MODEL, "input": texts, "encoding_format": "float"}).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())

# 1. dimension + usage
t0 = time.time()
r = call(["hello world", "another sentence here"])
dt = time.time() - t0
dim = len(r["data"][0]["embedding"])
print("dimension:", dim)
print("usage:", r.get("usage"))
print("latency 2 items: %.2fs" % dt)
print("vec head:", r["data"][0]["embedding"][:3])

# 2. batch size test: 128 items
t0 = time.time()
r2 = call(["batch test sentence number %d with some padding words here" % i for i in range(128)])
dt2 = time.time() - t0
print("128 items: %.2fs (%.1f items/s)" % (dt2, 128 / dt2))
print("usage128:", r2.get("usage"))

# 3. long text (does it truncate? 8k chars)
long_text = "long text test " * 2000  # ~28k chars
t0 = time.time()
r3 = call([long_text])
dt3 = time.time() - t0
print("long 28k-char item: %.2fs usage=%s" % (dt3, r3.get("usage")))
'''

def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=15)
    sftp = client.open_sftp()
    with sftp.open("/tmp/_probe_emb.py", "w") as f:
        f.write(REMOTE_SCRIPT)
    sftp.close()
    try:
        _, stdout, stderr = client.exec_command("python3 /tmp/_probe_emb.py", timeout=300)
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
