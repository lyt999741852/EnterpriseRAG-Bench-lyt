"""Check v2 build progress (448+32 -> 31920) on the server."""
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
            "procs": r"ps -ef | grep -E '_run_build_v2_daemon|src\.build_es_index' | grep -v grep || echo NONE",
            "attempts": r"grep -c 'starting build' /opt/enterprise-rag-bench/app/outputs/build_qwen3_emb_v2_20260806.log || echo 0",
            "log_tail": r"tail -n 12 /opt/enterprise-rag-bench/app/outputs/build_qwen3_emb_v2_20260806.log",
            "ckpt": r"cat /opt/enterprise-rag-bench/app/.index_cache/full_es_qwen3_emb/es_build_progress.json 2>/dev/null || echo NO_CHECKPOINT",
            "cache_chunks": r"wc -l /opt/enterprise-rag-bench/app/.index_cache/full_es_qwen3_emb/chunks.jsonl 2>/dev/null || echo NO_CHUNKS",
            "cache_manifest": r"sqlite3 /opt/enterprise-rag-bench/app/.index_cache/full_es_qwen3_emb/manifest.sqlite3 'SELECT COUNT(*) FROM documents;' 2>/dev/null || echo NO_MANIFEST",
            "count_v2": r"curl -fsS --max-time 15 'http://10.72.100.29:31920/enterprise-rag-qwen3-emb-v2/_count' 2>/dev/null || echo NO_INDEX",
            "index_cat": r"curl -fsS --max-time 15 'http://10.72.100.29:31920/_cat/indices/enterprise-rag-qwen3-emb-v2?v&h=health,status,index,pri,rep,docs.count,docs.deleted,store.size,creation.date.string' 2>/dev/null || echo NO_INDEX_STATS",
            "indexing_stats": r"curl -fsS --max-time 15 'http://10.72.100.29:31920/enterprise-rag-qwen3-emb-v2/_stats/docs,indexing?filter_path=indices.*.primaries.docs,indices.*.primaries.indexing' 2>/dev/null || echo NO_INDEXING_STATS",
            "es_health": r"curl -fsS --max-time 15 'http://10.72.100.29:31920/_cluster/health' 2>/dev/null | head -c 300 || echo UNREACHABLE",
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
