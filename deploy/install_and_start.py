"""Install dependencies and start 500-question evaluation."""
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
    # Install missing dependencies
    print("=== Installing dependencies ===")
    stdin, stdout, stderr = client.exec_command(
        "pip install rank-bm25 elasticsearch 2>&1 | tail -5",
        timeout=120
    )
    print(stdout.read().decode())

    # Verify installation
    stdin, stdout, stderr = client.exec_command(
        "python3 -c 'import rank_bm25; import elasticsearch; print(\"OK: rank_bm25 + elasticsearch\")'",
        timeout=10
    )
    print(stdout.read().decode().strip())
    err = stderr.read().decode().strip()
    if err:
        print(f"STDERR: {err[:300]}")

    # Check if elasticsearch module is used by the backend
    print("\n=== Starting pipeline ===")
    cmd = (
        f"cd {REMOTE_APP} && "
        f"export LARK_API_KEY=lark && "
        f"nohup python3 -m src.pipeline configs/eval_500_es_qwen_v2.yaml "
        f"> outputs/eval_500_run.log 2>&1 & echo $!"
    )
    stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
    pid = stdout.read().decode().strip()
    print(f"Pipeline started with PID: {pid}")

    # Wait and check
    time.sleep(5)
    stdin, stdout, stderr = client.exec_command(
        f"ps aux | grep 'src.pipeline' | grep -v grep",
        timeout=10
    )
    ps_out = stdout.read().decode().strip()
    if ps_out:
        print(f"Process running:\n{ps_out}")
    else:
        print("Process not running. Log:")
        stdin, stdout, stderr = client.exec_command(
            f"tail -30 {REMOTE_APP}/outputs/eval_500_run.log",
            timeout=10
        )
        print(stdout.read().decode())

    # Show initial log output
    print("\n=== Initial log (first 30 lines) ===")
    stdin, stdout, stderr = client.exec_command(
        f"head -30 {REMOTE_APP}/outputs/eval_500_run.log",
        timeout=10
    )
    print(stdout.read().decode())

finally:
    client.close()
