"""Start 500-question evaluation with proper background handling."""
import os
import paramiko
import time

HOST = "10.72.100.29"
USER = "root"
PASS = os.environ.get("SSH_PASS", "")
REMOTE_APP = "/opt/enterprise-rag-bench/app"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=22, username=USER, password=PASS, timeout=15)

try:
    # Use bash -c to properly background the process
    cmd = (
        f'bash -c \'cd {REMOTE_APP} && '
        f'export LARK_API_KEY=lark && '
        f'nohup python3 -m src.pipeline configs/eval_500_es_qwen_v2.yaml '
        f'> outputs/eval_500_run.log 2>&1 & disown; echo STARTED:$!\' '
    )
    stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
    result = stdout.read().decode().strip()
    print(f"Start result: {result}")

    time.sleep(8)

    # Check if running
    stdin, stdout, stderr = client.exec_command(
        "ps aux | grep 'src.pipeline' | grep -v grep",
        timeout=10
    )
    ps_out = stdout.read().decode().strip()
    if ps_out:
        print(f"Process confirmed running:\n{ps_out}")
    else:
        print("Process NOT running. Checking log...")

    # Show log regardless
    print("\n=== Log output ===")
    stdin, stdout, stderr = client.exec_command(
        f"tail -40 {REMOTE_APP}/outputs/eval_500_run.log",
        timeout=10
    )
    print(stdout.read().decode())

finally:
    client.close()
