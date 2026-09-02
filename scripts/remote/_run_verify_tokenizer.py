"""Upload and run the tokenizer verification script on the server."""
import os
import sys
from pathlib import Path

import paramiko

LOCAL = Path(r"d:\EnterpriseRAG-Bench\scripts\diag\_verify_tokenizer.py")
REMOTE = "/opt/enterprise-rag-bench/app/scripts/diag/_verify_tokenizer.py"


def main() -> int:
    password = os.environ.get("SSH_PASS", "") or "XAznv@(2018)"
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("10.72.100.29", username="root", password=password, timeout=15)
    try:
        client.exec_command(f"mkdir -p /opt/enterprise-rag-bench/app/scripts/diag")
        sftp = client.open_sftp()
        sftp.put(str(LOCAL), REMOTE)
        sftp.close()
        print("uploaded")
        _, stdout, stderr = client.exec_command(
            f"/root/anaconda3/envs/embedding_test/bin/python {REMOTE}",
            timeout=600,
        )
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        print(out)
        if err:
            print(f"[stderr] {err[-2000:]}")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
