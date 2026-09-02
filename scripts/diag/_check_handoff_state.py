"""One-shot state check for the vector-rebuild handoff (2026-08-06).

Connects to 10.72.100.29 via SSH (password from env SSH_PASS) and reports:
- server-side build config (which ES it targets)
- build process liveness
- ES doc counts on both 127.0.0.1:9200 and 10.72.100.29:31920
- checkpoint file, automation log tail, build log tail, lock state
"""
import os
import sys

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
            "build_proc": r'pgrep -af "src.build_es_index" || echo NONE',
            "srv_yaml_es": r"grep -A5 '^elasticsearch:' /opt/enterprise-rag-bench/app/configs/full_es_qwen3_emb.yaml",
            "srv_yaml_chunk": r"grep -A5 '^chunking:' /opt/enterprise-rag-bench/app/configs/full_es_qwen3_emb.yaml",
            "count_127": r"curl -fsS --max-time 15 'http://127.0.0.1:9200/enterprise-rag-qwen3-emb-v1/_count' 2>/dev/null || echo UNREACHABLE",
            "count_31920": r"curl -fsS --max-time 15 'http://10.72.100.29:31920/enterprise-rag-qwen3-emb-v1/_count' 2>/dev/null || echo UNREACHABLE",
            "ckpt": r"cat /opt/enterprise-rag-bench/app/.index_cache/full_es_qwen3_emb/es_build_progress.json 2>/dev/null || echo NO_CHECKPOINT",
            "auto_log_tail": r"tail -n 15 /opt/enterprise-rag-bench/app/outputs/q3emb50_automation.log 2>/dev/null || echo NO_LOG",
            "build_log_tail": r"tail -n 15 /opt/enterprise-rag-bench/app/outputs/build_qwen3_emb_20260805.log 2>/dev/null || echo NO_LOG",
            "lock": r"ls -la /opt/enterprise-rag-bench/app/outputs/q3emb50_automation.lock 2>/dev/null || echo NO_LOCK",
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
    sys.exit(main())
