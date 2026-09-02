"""Diagnose where the v2 build process is stuck (network connections)."""
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
            "now": "date '+%F %T %z'",
            "proc": r"ps -o pid,etime,time,%cpu,rss,cmd -p $(pgrep -f 'src.build_es_index configs/full_es_qwen3_emb.yaml' | head -1)",
            "log_tail": r"tail -n 8 /opt/enterprise-rag-bench/app/outputs/build_qwen3_emb_v2_20260806.log",
            "conns": r"ss -tnp 2>/dev/null | grep -E '7993|31920|9200' || echo NO_MATCH",
            "mget_timing": r"time curl -fsS -X POST 'http://10.72.100.29:31920/enterprise-rag-qwen3-emb-v2/_mget?_source=false' -H 'Content-Type: application/json' -d '{\"ids\":[\"smoke__chunk00000\",\"smoke__chunk00001\",\"smoke__chunk00002\"]}' -o /dev/null -w '%{time_total}s' 2>&1 || echo MGET_FAIL",
            "embed_timing": r"time curl -fsS -X POST 'http://10.72.55.209:7993/v1/embeddings' -H 'Content-Type: application/json' -H 'Authorization: Bearer 123456' -d '{\"model\":\"embedding\",\"input\":[\"hello world\"],\"encoding_format\":\"float\"}' -o /dev/null -w '%{time_total}s' 2>&1 || echo EMBED_FAIL",
        }
        for name, cmd in cmds.items():
            out, err = run(client, cmd, timeout=120)
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
