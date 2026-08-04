"""Start the 500-question evaluation on the remote server."""
import os
import paramiko
import sys
import time

HOST = "10.72.100.29"
USER = "root"
PASS = os.environ.get("SSH_PASS", "")
REMOTE_APP = "/opt/enterprise-rag-bench/app"
LOCAL_ROOT = r"d:\EnterpriseRAG-Bench"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=22, username=USER, password=PASS, timeout=15)
sftp = client.open_sftp()

try:
    # Re-sync the updated config (device: cuda:1)
    local_cfg = LOCAL_ROOT + r"\configs\eval_500_es_qwen_v2.yaml"
    remote_cfg = f"{REMOTE_APP}/configs/eval_500_es_qwen_v2.yaml"
    sftp.put(local_cfg, remote_cfg)
    print(f"Config synced (device: cuda:1)")

    # Check how python is set up on the server
    print("\n--- Checking Python environment ---")
    stdin, stdout, stderr = client.exec_command(
        f"cd {REMOTE_APP} && which python3 && python3 --version && pip list 2>/dev/null | grep -i -E 'torch|sentence|faiss|elasticsearch|rank.bm25|yaml'",
        timeout=15
    )
    print(stdout.read().decode())
    err = stderr.read().decode()
    if err:
        print(f"STDERR: {err[:500]}")

    # Check if there's an existing eval_500 output directory
    print("\n--- Checking existing 500 outputs ---")
    stdin, stdout, stderr = client.exec_command(
        f"ls -la {REMOTE_APP}/outputs/eval_500* 2>/dev/null || echo 'No eval_500 outputs yet'",
        timeout=10
    )
    print(stdout.read().decode())

    # Check LARK_API_KEY environment variable
    print("\n--- Checking env vars ---")
    stdin, stdout, stderr = client.exec_command(
        "env | grep -i -E 'LARK|API_KEY|DEEPSEEK' | sed 's/=.*/=***/'",
        timeout=10
    )
    env_out = stdout.read().decode()
    print(env_out if env_out.strip() else "No API key env vars found")

    print("\n--- Starting 500-question pipeline (background) ---")
    # Start the pipeline in background with nohup
    cmd = (
        f"cd {REMOTE_APP} && "
        f"export LARK_API_KEY=lark && "
        f"nohup python3 -m src.pipeline configs/eval_500_es_qwen_v2.yaml "
        f"> outputs/eval_500_run.log 2>&1 & echo $!"
    )
    stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
    pid = stdout.read().decode().strip()
    print(f"Pipeline started with PID: {pid}")
    time.sleep(3)

    # Verify it's running
    stdin, stdout, stderr = client.exec_command(f"ps aux | grep 'src.pipeline' | grep -v grep", timeout=10)
    ps_out = stdout.read().decode()
    if ps_out:
        print(f"Process confirmed running:\n{ps_out.strip()}")
    else:
        print("WARNING: Process may have exited already. Checking log...")
        stdin, stdout, stderr = client.exec_command(
            f"tail -50 {REMOTE_APP}/outputs/eval_500_run.log 2>/dev/null",
            timeout=10
        )
        print(stdout.read().decode())

finally:
    sftp.close()
    client.close()
