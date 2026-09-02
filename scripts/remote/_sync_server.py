"""Sync v5 fixed files to the server via SFTP (password from env SSH_PASS)."""
import os
import sys
from pathlib import Path

import paramiko

LOCAL_ROOT = Path(r"d:\EnterpriseRAG-Bench")
REMOTE_ROOT = "/opt/enterprise-rag-bench/app"

FILES = [
    "src/pageindex_router.py",
    "src/generator.py",
    "tests/test_core.py",
]


def main() -> int:
    password = os.environ.get("SSH_PASS", "")
    if not password:
        print("SSH_PASS env var is required")
        return 2
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("10.72.100.29", username="root", password=password, timeout=15)
    sftp = client.open_sftp()
    try:
        for relative in FILES:
            local = LOCAL_ROOT / relative
            remote = f"{REMOTE_ROOT}/{relative}"
            sftp.put(str(local), remote)
            print(f"uploaded: {relative}")
    finally:
        sftp.close()
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
