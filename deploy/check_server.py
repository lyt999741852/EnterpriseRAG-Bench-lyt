"""SSH check script for remote server services."""
import os
import paramiko
import sys

HOST = "10.72.100.29"
USER = "root"
PASS = os.environ.get("SSH_PASS", "")

commands = [
    "echo '=== SSH Connection OK ==='",
    "echo '--- ES Health ---'",
    "curl -s http://127.0.0.1:9200/_cluster/health 2>/dev/null || echo 'ES_DOWN'",
    "echo ''",
    "echo '--- ES Index Count ---'",
    "curl -s http://127.0.0.1:9200/enterprise-rag-bge-small-v1/_count 2>/dev/null || echo 'INDEX_MISSING'",
    "echo ''",
    "echo '--- Qwen LLM ---'",
    "curl -s -X POST http://10.72.100.35:7777/v1/chat/completions -H 'Content-Type: application/json' -H 'Authorization: Bearer lark' -d '{\"model\":\"lark\",\"messages\":[{\"role\":\"user\",\"content\":\"hello\"}],\"max_tokens\":10}' 2>/dev/null | head -c 300 || echo 'QWEN_DOWN'",
    "echo ''",
    "echo '--- App Directory ---'",
    "ls -la /opt/enterprise-rag-bench/app/ 2>/dev/null | head -20 || echo 'APP_DIR_MISSING'",
    "echo '--- PageIndex ---'",
    "ls /opt/enterprise-rag-bench/PageIndex/ 2>/dev/null | head -5 || echo 'PAGEINDEX_MISSING'",
    "echo '--- Disk Space ---'",
    "df -h / | tail -1",
    "echo '--- GPU ---'",
    "nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv,noheader 2>/dev/null || echo 'NO_GPU'",
    "echo '--- Python venv ---'",
    "ls /opt/enterprise-rag-bench/app/venv/bin/python 2>/dev/null || echo 'NO_VENV'",
    "echo '--- Existing outputs ---'",
    "ls /opt/enterprise-rag-bench/app/outputs/ 2>/dev/null | tail -10 || echo 'NO_OUTPUTS'",
    "echo '=== DONE ==='",
]

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    client.connect(HOST, port=22, username=USER, password=PASS, timeout=15)
    full_cmd = " && ".join(commands)
    stdin, stdout, stderr = client.exec_command(full_cmd, timeout=30)
    print(stdout.read().decode("utf-8", errors="replace"))
    err = stderr.read().decode("utf-8", errors="replace")
    if err:
        print(f"STDERR: {err}", file=sys.stderr)
finally:
    client.close()
