"""Run commands on the server via SSH (password from env SSH_PASS)."""
import os
import sys

import paramiko


def run_remote(client: paramiko.SSHClient, command: str, timeout: int = 600) -> str:
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace").strip()
    err = stderr.read().decode("utf-8", "replace").strip()
    if out:
        print(out)
    if err:
        print(f"[stderr] {err}")
    return out


def main() -> int:
    password = os.environ.get("SSH_PASS", "")
    if not password:
        print("SSH_PASS env var is required")
        return 2
    command = os.environ.get("REMOTE_CMD", "")
    if not command:
        print("REMOTE_CMD env var is required")
        return 2
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("10.72.100.29", username="root", password=password, timeout=15)
    try:
        run_remote(client, command)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
