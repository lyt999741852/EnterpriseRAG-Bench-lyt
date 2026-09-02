"""Compare server-side src files with local copies (checksum + key markers)."""
import os
import hashlib

import paramiko


def run(client, command, timeout=60):
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace").strip()
    err = stderr.read().decode("utf-8", "replace").strip()
    return out, err


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def main() -> int:
    password = os.environ.get("SSH_PASS", "") or "XAznv@(2018)"
    files = [
        "src/embedder.py",
        "src/elasticsearch_backend.py",
        "src/indexer.py",
        "src/build_es_index.py",
        "src/pipeline.py",
    ]
    local_dir = r"d:\EnterpriseRAG-Bench"
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("10.72.100.29", username="root", password=password, timeout=15)
    try:
        for rel in files:
            local_md5 = md5(os.path.join(local_dir, rel))
            out, err = run(client, f"md5sum /opt/enterprise-rag-bench/app/{rel}")
            server_md5 = out.split()[0] if out else "MISSING"
            same = "SAME" if local_md5 == server_md5 else "*** DIFFERENT ***"
            print(f"{rel}: local={local_md5} server={server_md5} -> {same}")
        # Marker checks on server copy
        markers = {
            "embedder_retry": r"grep -c 'after 3 attempts' /opt/enterprise-rag-bench/app/src/embedder.py",
            "es_ckpt": r"grep -c 'es_build_progress' /opt/enterprise-rag-bench/app/src/elasticsearch_backend.py",
        }
        for name, cmd in markers.items():
            out, _ = run(client, cmd)
            print(f"server marker {name}: {out}")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    main()
