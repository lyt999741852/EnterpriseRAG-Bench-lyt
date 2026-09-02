"""Stop the v2 build daemon + build process on the server."""
import os
import time

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
        # 1. Stop the daemon first (otherwise it would restart the build).
        run(client, "pkill -f '^bash /opt/enterprise-rag-bench/app/scripts/start/_run_build_v2_daemon.sh' || true", timeout=30)
        time.sleep(2)
        # 2. Stop the build itself.
        run(client, "pkill -f 'src.build_es_index configs/full_es_qwen3_emb.yaml' || true", timeout=30)
        time.sleep(3)
        # 3. Verify both are gone.
        out, _ = run(client, r"ps -ef | grep -E '_run_build_v2_daemon|src\.build_es_index' | grep -v grep || echo ALL_STOPPED")
        print("=== after stop ===")
        print(out)
        out, _ = run(client, r"cat /opt/enterprise-rag-bench/app/.index_cache/full_es_qwen3_emb/es_build_progress.json")
        print("=== checkpoint (resume point) ===")
        print(out)
        out, _ = run(client, r"curl -fsS --max-time 15 'http://10.72.100.29:31920/enterprise-rag-qwen3-emb-v2/_count' 2>/dev/null || echo NO_INDEX")
        print("=== v2 index count ===")
        print(out)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    main()
