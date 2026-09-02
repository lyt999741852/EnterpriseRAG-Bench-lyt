"""Upload the explicitly listed D2b implementation files to the eval host."""

from __future__ import annotations

import argparse
from pathlib import Path

import paramiko


ROOT = Path(__file__).resolve().parents[2]
REMOTE_ROOT = "/opt/enterprise-rag-bench/app"
FILES = [
    "src/pipeline.py",
    "configs/eval_semantic30_r4_d2b_e5_secondary_20260825.yaml",
    "scripts/remote/_launch_semantic30_r4_d2b_e5_secondary_20260825.sh",
    "scripts/remote/_status_semantic30_r4_d2b_e5_secondary_20260825.sh",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password-codes", nargs="+", type=int, required=True)
    args = parser.parse_args()
    password = "".join(chr(code) for code in args.password_codes)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(args.host, username=args.user, password=password, timeout=20)
    try:
        with client.open_sftp() as sftp:
            for relative in FILES:
                local = ROOT / relative
                remote = f"{REMOTE_ROOT}/{relative}"
                sftp.put(str(local), remote)
                print(f"uploaded: {relative}")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
