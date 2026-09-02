"""Second-pass state check: automation liveness + 31920 reachability details."""
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
            "auto_proc": r'ps -ef | grep -E "q3emb50_automation|_run_q3emb50" | grep -v grep || echo NONE',
            "build_proc": r'ps -ef | grep -E "src\.build_es_index" | grep -v grep || echo NONE',
            "auto_log_all": r'wc -l /opt/enterprise-rag-bench/app/outputs/q3emb50_automation.log; tail -n 5 /opt/enterprise-rag-bench/app/outputs/q3emb50_automation.log',
            "count_172": r"curl -fsS --max-time 15 'http://172.16.186.245:31920/enterprise-rag-qwen3-emb-v1/_count' 2>/dev/null || echo UNREACHABLE",
            "es_ver_127": r"curl -fsS --max-time 10 'http://127.0.0.1:9200/' 2>/dev/null | head -c 400 || echo UNREACHABLE",
            "es_ver_31920": r"curl -fsS --max-time 10 'http://10.72.100.29:31920/' 2>/dev/null | head -c 400 || echo UNREACHABLE",
            "listen_31920": r"ss -ltnp 2>/dev/null | grep 31920 || echo NOT_LISTENING",
            "docker_es": r"docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep -iE 'es|elastic' || echo NO_ES_CONTAINER",
            "k8s_svc": r"kubectl get svc -A 2>/dev/null | grep -iE '31920|vector|es-' || echo NO_K8S_SVC_MATCH",
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
