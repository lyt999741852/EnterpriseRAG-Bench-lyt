"""Summarize index build reports/log failures for O3.3 (read-only)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.request import urlopen


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def report_summary(path: Path) -> dict:
    data = load_json(path)
    return {
        "path": str(path),
        "cluster_status_in_report": data.get("cluster_status"),
        "preprocess": {
            "num_docs": data.get("preprocess", {}).get("num_docs"),
            "num_chunks": data.get("preprocess", {}).get("num_chunks"),
            "failed_files": data.get("preprocess", {}).get("failed_files"),
            "duplicate_doc_ids": data.get("preprocess", {}).get("duplicate_doc_ids"),
        },
        "indexing": data.get("indexing", {}),
        "es_count": data.get("es_count"),
    }


def live_health(url: str, index: str) -> dict:
    try:
        with urlopen(url.rstrip("/") + f"/_cluster/health/{index}", timeout=30) as response:
            data = json.loads(response.read().decode())
        return {key: data.get(key) for key in ("status", "number_of_nodes", "active_primary_shards", "unassigned_shards")}
    except Exception as exc:  # diagnostic output should preserve the failure
        return {"error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bge-cache", type=Path, required=True)
    parser.add_argument("--conan-cache", type=Path, required=True)
    parser.add_argument("--conan-log", type=Path, required=True)
    parser.add_argument("--o32-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bge-es", default="http://127.0.0.1:9200")
    parser.add_argument("--conan-es", default="http://10.72.100.29:31920")
    args = parser.parse_args()

    reports = {
        "bge": sorted(args.bge_cache.glob("es_build_report*.json")),
        "conan": sorted(args.conan_cache.glob("es_build_report*.json")),
    }
    report_data = {
        model: [report_summary(path) for path in paths]
        for model, paths in reports.items()
    }
    log_text = args.conan_log.read_text(encoding="utf-8", errors="replace")
    traceback_count = log_text.count("Traceback (most recent call last):")
    timeout_count = len(re.findall(r"TimeoutError: timed out", log_text))
    bulk_failure_count = len(re.findall(r"bulk indexing failed", log_text, flags=re.IGNORECASE))
    explicit_failure_lines = [
        line.strip() for line in log_text.splitlines()
        if re.search(r"bulk indexing failed|failed=[1-9]|RuntimeError:|ConnectionError:", line, re.IGNORECASE)
    ][:30]
    progress_path = args.conan_cache / "es_build_progress.json"
    progress = load_json(progress_path) if progress_path.exists() else {}
    o32 = load_json(args.o32_output)

    output = {
        "schema_version": 1,
        "scope": "O3.3 index build and bulk failure audit",
        "reports": report_data,
        "cache_failed_files_bytes": {
            "bge": (args.bge_cache / "failed_files.jsonl").stat().st_size,
            "conan": (args.conan_cache / "failed_files.jsonl").stat().st_size,
        },
        "conan_log": {
            "traceback_count": traceback_count,
            "embedding_timeout_count": timeout_count,
            "bulk_failure_count": bulk_failure_count,
            "explicit_failure_lines": explicit_failure_lines,
        },
        "conan_progress": progress,
        "live_health": {
            "bge": live_health(args.bge_es, "enterprise-rag-bge-small-v1"),
            "conan": live_health(args.conan_es, "enterprise-rag-qwen3-emb-v3-conan448"),
        },
        "o32_coverage": {
            model: {
                "index_doc_count": value.get("index_doc_count"),
                "index_missing_doc_ids": value.get("index_missing_doc_ids", []),
                "o31_layer_counts": value.get("o31_layer_counts", {}),
            }
            for model, value in o32.get("aggregate", {}).items()
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
