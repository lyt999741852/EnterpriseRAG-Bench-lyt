"""Check tiktoken availability in conda envs + embedding API batch scaling."""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import paramiko

PASSWORD = "XAznv@(2018)"
HOST = "10.72.100.29"

REMOTE_SCRIPT = r'''
import importlib.util

for env_name, py in [
    ("embedding_test", "/root/anaconda3/envs/embedding_test/bin/python"),
    ("base", "/root/anaconda3/bin/python"),
]:
    import subprocess
    r = subprocess.run([py, "-c", "import tiktoken; print('tiktoken OK')"],
                       capture_output=True, text=True, timeout=60)
    print(f"{env_name}: {r.stdout.strip() or r.stderr.strip()[:200]}")

# embedding API: batch 256 scaling + max length check
import json
import time
import urllib.request

URL = "http://10.72.55.209:7993/v1/embeddings"
KEY = "123456"

def call(texts):
    body = json.dumps({"model": "embedding", "input": texts}).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())

# batch 256
t0 = time.time()
r = call(["batch item number %d with realistic enterprise text length" % i for i in range(256)])
dt = time.time() - t0
print("batch 256: %.2fs (%.1f items/s)" % (dt, 256 / dt))

# length limit: 2000 / 4000 / 8000 tokens approx
for n_tokens in [2000, 4000, 8000]:
    text = ("word " * n_tokens).strip()
    try:
        t0 = time.time()
        r = call([text])
        print(f"len {n_tokens} tokens: OK %.2fs usage=%s" % (time.time() - t0, r.get("usage")))
    except Exception as e:
        print(f"len {n_tokens} tokens: FAIL {e}")
'''

def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=15)
    sftp = client.open_sftp()
    with sftp.open("/tmp/_probe2.py", "w") as f:
        f.write(REMOTE_SCRIPT)
    sftp.close()
    try:
        _, stdout, stderr = client.exec_command("python3 /tmp/_probe2.py", timeout=600)
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
