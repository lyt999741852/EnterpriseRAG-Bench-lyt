"""Fetch the first N lines of the server's real v2 chunks.jsonl for local benchmarking."""
import os

import paramiko

REMOTE = "/opt/enterprise-rag-bench/app/.index_cache/full_es_qwen3_emb/chunks.jsonl"
LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_sample_v2_chunks.jsonl")
N = 2048


def main() -> int:
    password = os.environ.get("SSH_PASS", "") or "XAznv@(2018)"
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("10.72.100.29", username="root", password=password, timeout=15)
    try:
        sftp = client.open_sftp()
        with sftp.open(REMOTE, "r") as remote:
            with open(LOCAL, "w", encoding="utf-8") as local:
                for i, line in enumerate(remote):
                    local.write(line)
                    if i >= N - 1:
                        break
        sftp.close()
        print(f"saved {N} lines to {LOCAL}")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    main()
