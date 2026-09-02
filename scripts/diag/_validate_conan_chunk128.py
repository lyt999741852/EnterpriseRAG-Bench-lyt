"""Read-only 128+16 Conan input-limit validation on 1,000 corpus documents.

Runs on the build server. It does not write cache files or Elasticsearch data.
"""

from __future__ import annotations

import os
import sys

import paramiko


REMOTE_SCRIPT = r'''
import json
import os
import re
import sqlite3
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = "/opt/enterprise-rag-bench/app"
MANIFEST = ROOT + "/.index_cache/full_es_qwen3_emb/manifest.sqlite3"
API = "http://10.72.55.209:7993/v1/embeddings"
KEY = "123456"
SIZE = __CHUNK_SIZE__
OVERLAP = __CHUNK_OVERLAP__
DOC_LIMIT = __DOC_LIMIT__

def chunks(text):
    words = list(re.finditer(r"\S+", text))
    if not words:
        return []
    step = SIZE - OVERLAP
    return [text[words[start].start():words[min(start + SIZE, len(words)) - 1].end()]
            for start in range(0, len(words), step)]

conn = sqlite3.connect(MANIFEST)
rows = conn.execute("SELECT file_path FROM documents WHERE status='chunked' ORDER BY doc_id LIMIT ?", (DOC_LIMIT,)).fetchall()
conn.close()
texts = []
for (path,) in rows:
    try:
        with open(os.path.join(ROOT, "corpus/all_documents", path), encoding="utf-8", errors="replace") as f:
            texts.extend(chunks(f.read()))
    except OSError:
        pass

lock = threading.Lock()
result = {"ok": 0, "over_512": 0, "other_error": 0, "max_reported_tokens": 0, "examples": []}
cursor = 0

def check(text):
    payload = json.dumps({"model":"embedding", "input":[text], "encoding_format":"float"}).encode()
    req = urllib.request.Request(API, data=payload, headers={"Content-Type":"application/json", "Authorization":"Bearer " + KEY})
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return "ok", int(json.loads(response.read().decode()).get("usage", {}).get("prompt_tokens", 0))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        match = re.search(r"has (\d+) input tokens", detail)
        return ("over", int(match.group(1))) if exc.code == 400 and match else ("error", exc.code)
    except Exception as exc:
        return "error", type(exc).__name__

def worker():
    global cursor
    while True:
        with lock:
            if cursor >= len(texts): return
            pos = cursor; cursor += 1
        status, detail = check(texts[pos])
        with lock:
            if status == "ok": result["ok"] += 1
            elif status == "over":
                result["over_512"] += 1
                result["max_reported_tokens"] = max(result["max_reported_tokens"], detail)
                if len(result["examples"]) < 5: result["examples"].append({"chars":len(texts[pos]), "api_tokens":detail})
            else: result["other_error"] += 1

with ThreadPoolExecutor(max_workers=8) as pool:
    list(pool.map(lambda _: worker(), range(8)))
print(json.dumps({"documents": len(rows), "size": SIZE, "overlap": OVERLAP, "raw_chunks": len(texts), **result}, indent=2))
'''


def main() -> int:
    chunk_size = int(os.environ.get("CHUNK_SIZE", "128"))
    chunk_overlap = int(os.environ.get("CHUNK_OVERLAP", "16"))
    doc_limit = int(os.environ.get("DOC_LIMIT", "1000"))
    remote_script = (REMOTE_SCRIPT
        .replace("__CHUNK_SIZE__", str(chunk_size))
        .replace("__CHUNK_OVERLAP__", str(chunk_overlap))
        .replace("__DOC_LIMIT__", str(doc_limit)))
    password = os.environ.get("SSH_PASS", "") or "XAznv@(2018)"
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("10.72.100.29", username="root", password=password, timeout=15)
    try:
        stdin, stdout, stderr = client.exec_command("python3 -", timeout=1800)
        stdin.write(remote_script)
        stdin.channel.shutdown_write()
        print(stdout.read().decode("utf-8", "replace"))
        err = stderr.read().decode("utf-8", "replace")
        if err:
            print(err)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
