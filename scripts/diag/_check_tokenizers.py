"""List tokenizers available on the server (embedding_test + base env)."""
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
            "hub": r"ls /root/.cache/huggingface/hub 2>/dev/null | head -40 || echo NO_HUB",
            "old_cache": r"ls /root/.cache/huggingface/transformers 2>/dev/null | head -40 || echo NO_OLD",
            "qwen_pkgs": r"/root/anaconda3/envs/embedding_test/bin/pip list 2>/dev/null | grep -iE 'transformers|tokenizers|qwen' || echo NONE",
            "build_proc": r"ps -ef | grep src.build_es_index | grep -v grep || echo NONE",
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
