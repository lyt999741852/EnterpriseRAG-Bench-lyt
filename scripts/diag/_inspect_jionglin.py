"""Inspect the jionglin-embedding cache directory structure on the server."""
import os

import paramiko


def run(client, command, timeout=60):
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace").strip()
    err = stderr.read().decode("utf-8", "replace").strip()
    return out, err


def main() -> int:
    password = os.environ.get("SSH_PASS", "") or "XAznv@(2018)"
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("10.72.100.29", username="root", password=password, timeout=15)
    try:
        cmds = {
            "tree": r"find /root/.cache/huggingface/hub/models--sentosa--jionglin-embedding -type f | head -30",
            "dirs": r"find /root/.cache/huggingface/hub/models--sentosa--jionglin-embedding -maxdepth 3 -type d",
        }
        for name, cmd in cmds.items():
            out, err = run(client, cmd)
            print(f"===== {name} =====")
            print(out)
            if err:
                print(f"[stderr] {err}")
            print()
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    main()
