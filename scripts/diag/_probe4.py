"""Binary-search the exact length limit of the embedding API."""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import paramiko

PASSWORD = "XAznv@(2018)"
HOST = "10.72.100.29"

REMOTE_SCRIPT = r'''
import json
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

def probe_tokens(n):
    text = ("word " * n).strip()   # approx n tokens
    try:
        r = call([text])
        return r.get("usage", {}).get("total_tokens")
    except urllib.error.HTTPError:
        return None

# fine-grained token limit
for n in [256, 320, 384, 448, 480, 496, 504, 512]:
    t = probe_tokens(n)
    print(f"{n} words: {'OK tokens=' + str(t) if t else 'FAIL'}")

# character-level check with short repeated token "a"
def probe_chars(c):
    text = "a" * c
    try:
        r = call([text])
        return r.get("usage", {}).get("total_tokens")
    except urllib.error.HTTPError:
        return None

print("--- char-level ---")
for c in [1000, 1500, 2000, 2500]:
    t = probe_chars(c)
    print(f"{c} chars: {'OK tokens=' + str(t) if t else 'FAIL'}")
'''

def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=15)
    sftp = client.open_sftp()
    with sftp.open("/tmp/_probe4.py", "w") as f:
        f.write(REMOTE_SCRIPT)
    sftp.close()
    try:
        _, stdout, stderr = client.exec_command("python3 /tmp/_probe4.py", timeout=600)
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
