"""Sync config and source files to server, then start 500-question evaluation."""
import paramiko
import os

HOST = "10.72.100.29"
USER = "root"
PASS = os.environ.get("SSH_PASS", "")
REMOTE_APP = "/opt/enterprise-rag-bench/app"
LOCAL_ROOT = r"d:\EnterpriseRAG-Bench"

# Files to sync
files_to_sync = [
    ("configs/eval_500_es_qwen_v2.yaml", "configs/eval_500_es_qwen_v2.yaml"),
]

# Source files to sync
src_files = [
    "src/__init__.py",
    "src/pipeline.py",
    "src/indexer.py",
    "src/embedder.py",
    "src/retriever.py",
    "src/generator.py",
    "src/evaluator.py",
    "src/llm.py",
    "src/elasticsearch_backend.py",
    "src/pageindex_router.py",
    "src/validate_submission.py",
    "src/benchmark_embedding.py",
    "src/build_es_index.py",
]

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=22, username=USER, password=PASS, timeout=15)
sftp = client.open_sftp()

try:
    # Sync config
    for local_rel, remote_rel in files_to_sync:
        local_path = os.path.join(LOCAL_ROOT, local_rel)
        remote_path = f"{REMOTE_APP}/{remote_rel}"
        print(f"Syncing: {local_rel} -> {remote_path}")
        sftp.put(local_path, remote_path)

    # Sync source files
    for src_file in src_files:
        local_path = os.path.join(LOCAL_ROOT, src_file)
        remote_path = f"{REMOTE_APP}/{src_file}"
        if os.path.exists(local_path):
            print(f"Syncing: {src_file}")
            sftp.put(local_path, remote_path)

    # Check what GPU is available for BGE embedding
    print("\n--- Checking GPU processes ---")
    stdin, stdout, stderr = client.exec_command(
        "nvidia-smi --query-compute-apps=pid,gpu_uuid,used_memory,process_name --format=csv,noheader 2>/dev/null | head -20",
        timeout=10
    )
    print(stdout.read().decode())

    # Check if there's a free GPU or if GPU 2 has enough space
    stdin, stdout, stderr = client.exec_command(
        "nvidia-smi --query-gpu=index,memory.free --format=csv,noheader",
        timeout=10
    )
    gpu_mem = stdout.read().decode().strip()
    print(f"GPU free memory:\n{gpu_mem}")

    print("\n--- Sync complete ---")
finally:
    sftp.close()
    client.close()
