"""Remote helper: upload files / run commands / tail logs on the GPU server.

Usage:
    python _remote.py upload <path> [<path> ...]
    python _remote.py download <path> [<path> ...]
    python _remote.py run "<shell command>" [--timeout SECONDS]
    python _remote.py status [<log_path>]
"""
import os
import shlex
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import paramiko

HOST = os.environ.get("SSH_HOST", "10.72.100.29")
USER = os.environ.get("SSH_USER", "root")
REMOTE_ROOT = "/opt/enterprise-rag-bench/app"

CONDA_PREFIX = (
    "source /root/anaconda3/etc/profile.d/conda.sh && conda activate embedding_test && "
    "export TRANSFORMERS_OFFLINE=1 CUDA_VISIBLE_DEVICES=2 "
)


def _connect() -> paramiko.SSHClient:
    password = os.environ.get("SSH_PASS")
    if not password:
        raise RuntimeError("SSH_PASS must be set in the environment")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=password, timeout=15)
    return client


def _execution_environment() -> dict[str, str]:
    """Forward only explicitly configured API credentials to a remote command."""
    return {
        name: value
        for name in ("EMBEDDING_API_KEY", "LARK_API_KEY")
        if (value := os.environ.get(name))
    }


def _execution_environment_exports() -> str:
    """Build ephemeral shell exports for SSH servers that reject env requests."""
    return " ".join(
        f"export {name}={shlex.quote(value)};"
        for name, value in _execution_environment().items()
    )


def cmd_upload(paths: list[str]) -> int:
    client = _connect()
    sftp = client.open_sftp()
    try:
        for relative in paths:
            local = Path(r"d:\EnterpriseRAG-Bench") / relative
            remote = f"{REMOTE_ROOT}/{relative}"
            sftp.put(str(local), remote)
            print(f"uploaded: {relative}")
    finally:
        sftp.close()
        client.close()
    return 0


def cmd_download(paths: list[str]) -> int:
    client = _connect()
    sftp = client.open_sftp()
    try:
        for relative in paths:
            relative_path = Path(relative)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                raise ValueError(f"download path must be a relative workspace path: {relative}")
            local = Path(r"d:\EnterpriseRAG-Bench") / relative_path
            remote = f"{REMOTE_ROOT}/{relative_path.as_posix()}"
            local.parent.mkdir(parents=True, exist_ok=True)
            sftp.get(remote, str(local))
            print(f"downloaded: {relative}")
    finally:
        sftp.close()
        client.close()
    return 0


def cmd_run(command: str, timeout: int) -> int:
    client = _connect()
    try:
        _, stdout, stderr = client.exec_command(
            f"cd {REMOTE_ROOT} && {CONDA_PREFIX} && "
            f"{_execution_environment_exports()} {command}",
            timeout=timeout,
        )
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        if out:
            print(out[-8000:])
        if err:
            print(f"[stderr] {err[-3000:]}")
    finally:
        client.close()
    return 0


def cmd_run_raw(command: str, timeout: int) -> int:
    """Run a command without the cd/conda prefix (for plain bash scripts)."""
    client = _connect()
    try:
        _, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        if out:
            print(out[-8000:])
        if err:
            print(f"[stderr] {err[-3000:]}")
    finally:
        client.close()
    return 0


def cmd_status(log_path: str | None) -> int:
    client = _connect()
    log = log_path or f"{REMOTE_ROOT}/outputs/latest.log"
    try:
        _, stdout, stderr = client.exec_command(
            f"tail -25 {log} 2>/dev/null; echo '---PROC---'; "
            f"ps aux | grep -E 'src.pipeline|pipeline.py' | grep -v grep | head -3",
            timeout=30,
        )
        out = stdout.read().decode("utf-8", "replace")
        if out:
            print(out)
    finally:
        client.close()
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    action = args[0]
    if action == "upload":
        return cmd_upload(args[1:])
    if action == "download":
        return cmd_download(args[1:])
    if action == "run":
        if len(args) < 2:
            print("usage: python _remote.py run '<cmd>' [--timeout 600]")
            return 2
        timeout = 600
        if "--timeout" in args:
            idx = args.index("--timeout")
            timeout = int(args[idx + 1])
        return cmd_run(args[1], timeout)
    if action == "run_raw":
        if len(args) < 2:
            print("usage: python _remote.py run_raw '<cmd>' [--timeout 600]")
            return 2
        timeout = 600
        if "--timeout" in args:
            idx = args.index("--timeout")
            timeout = int(args[idx + 1])
        return cmd_run_raw(args[1], timeout)
    if action == "status":
        return cmd_status(args[1] if len(args) > 1 else None)
    print(f"unknown action: {action}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
