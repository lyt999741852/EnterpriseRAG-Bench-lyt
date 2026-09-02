"""Deploy v2 build (448+32 -> 31920) to the server and start a detached
build daemon, then verify the process and ES doc count.

Local counterpart of the daemon script lives at
scripts/start/_run_build_v2_daemon.sh.
"""
import os
import sys
import time
from pathlib import Path

import paramiko

LOCAL_ROOT = Path(r"d:\EnterpriseRAG-Bench")
REMOTE_ROOT = "/opt/enterprise-rag-bench/app"

FILES = [
    "src/elasticsearch_backend.py",
    "src/embedder.py",
    "tests/test_core.py",
    "configs/full_es_qwen3_emb.yaml",
    "configs/mini_qwen3_emb.yaml",
    "configs/eval_pageindex_balanced50_q3emb.yaml",
]

DAEMON = """#!/usr/bin/env bash
# Detached build daemon for v2 (448+32 -> 10.72.100.29:31920), 2026-08-06.
# Restarts the build if it dies; safe because chunk_ids are deterministic
# and the backend skips already-indexed ids via _mget.
set -u
ROOT="/opt/enterprise-rag-bench/app"
CONFIG="configs/full_es_qwen3_emb.yaml"
LOG="$ROOT/outputs/build_qwen3_emb_v2_20260806.log"
LOCK="$ROOT/outputs/q3emb_v2_build_daemon.lock"
MAX_RESTARTS=30

cd "$ROOT" || exit 1

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[$(date -Is)] daemon already running" >&2
  exit 0
fi

export EMBEDDING_API_KEY=123456
export TRANSFORMERS_OFFLINE=1

restart=0
while true; do
  if pgrep -f "src.build_es_index $CONFIG" >/dev/null 2>&1; then
    sleep 60
    continue
  fi
  if [ "$restart" -ge "$MAX_RESTARTS" ]; then
    echo "[$(date -Is)] restart limit reached" >> "$LOG"
    break
  fi
  restart=$((restart + 1))
  echo "[$(date -Is)] starting build (attempt $restart)" >> "$LOG"
  setsid nohup /root/anaconda3/envs/embedding_test/bin/python -u -m src.build_es_index "$CONFIG" \
    >> "$LOG" 2>&1 < /dev/null &
  sleep 60
done
"""


def run(client, command, timeout=120):
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
        sftp = client.open_sftp()
        try:
            for relative in FILES:
                local = LOCAL_ROOT / relative
                remote = f"{REMOTE_ROOT}/{relative}"
                sftp.put(str(local), remote)
                print(f"uploaded: {relative}")
        finally:
            sftp.close()

        daemon_remote = f"{REMOTE_ROOT}/scripts/start/_run_build_v2_daemon.sh"
        out, err = run(client, f"mkdir -p {REMOTE_ROOT}/scripts/start")
        with client.open_sftp() as sftp:
            with sftp.open(daemon_remote, "w") as fh:
                fh.write(DAEMON)
        print(f"uploaded: scripts/start/_run_build_v2_daemon.sh")

        run(client, "pkill -f '^bash /opt/enterprise-rag-bench/app/scripts/start/_run_build_v2_daemon.sh' || true", timeout=30)
        time.sleep(1)
        out, err = run(client, f"setsid nohup bash {daemon_remote} >> {REMOTE_ROOT}/outputs/q3emb_v2_daemon_launch.log 2>&1 < /dev/null &", timeout=30)
        print("daemon relaunch output:", out or err or "(launched)")

        time.sleep(20)
        out, _ = run(client, r"ps -ef | grep -E 'build_es_index|build_v2_daemon' | grep -v grep || echo NONE")
        print("=== processes ===")
        print(out)
        out, _ = run(client, r"tail -n 5 " + f"{REMOTE_ROOT}/outputs/build_qwen3_emb_v2_20260806.log 2>/dev/null || echo NO_LOG_YET")
        print("=== build log tail ===")
        print(out)
        out, _ = run(client, r"curl -fsS --max-time 15 'http://10.72.100.29:31920/enterprise-rag-qwen3-emb-v2/_count' 2>/dev/null || echo NO_INDEX_YET")
        print("=== v2 index count ===")
        print(out)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
