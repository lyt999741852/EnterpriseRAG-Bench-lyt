"""Third-pass: find why build/automation died around 10:37 (2026-08-06)."""
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
            "build_log_tail": r"tail -n 40 /opt/enterprise-rag-bench/app/outputs/build_qwen3_emb_20260805.log",
            "build_log_restarts": r"grep -c 'restarting full index build' /opt/enterprise-rag-bench/app/outputs/q3emb50_automation.log || echo 0",
            "auto_log_restarts": r"grep -n 'restarting full index build\|build stopped\|automation started' /opt/enterprise-rag-bench/app/outputs/q3emb50_automation.log | tail -n 10",
            "dmesg_oom": r"dmesg -T 2>/dev/null | grep -iE 'oom|killed process' | tail -n 5 || echo NO_OOM",
            "kernel_log": r"journalctl -k --since '2026-08-06 10:30' --until '2026-08-06 10:45' 2>/dev/null | grep -iE 'oom|kill' | tail -n 5 || echo NO_JOURNAL",
            "syslog_tail": r"tail -n 20 /var/log/syslog 2>/dev/null | grep -iE 'oom|kill|python' || echo NO_SYSLOG_MATCH",
            "uptime": "uptime",
            "mem": r"free -h",
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
