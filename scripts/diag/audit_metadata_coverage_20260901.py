"""Audit corpus/manifest metadata provenance and current ES field coverage."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from collections import Counter
from pathlib import Path
from urllib.request import Request, urlopen


def request_json(url: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        url,
        data=data,
        method="POST" if payload is not None else "GET",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode())


def load_jsonl(path: Path) -> dict[str, dict]:
    return {
        str(row["question_id"]): row
        for row in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
        if row.get("question_id")
    }


def manifest_rows(path: Path) -> list[dict]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return [
            {
                "file_path": str(file_path or ""),
                "doc_id": str(doc_id or ""),
                "source_type": str(source_type or ""),
                "status": str(status or ""),
                "chunk_count": int(chunk_count or 0),
            }
            for file_path, doc_id, source_type, status, chunk_count in connection.execute(
                "SELECT file_path,doc_id,source_type,status,chunk_count FROM documents"
            )
        ]
    finally:
        connection.close()


def filename_title(file_path: str) -> str:
    name = Path(file_path).name
    stem = name.rsplit(".", 1)[0]
    return stem.split("__", 1)[1] if "__" in stem else stem


def first_nonempty_line(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            value = line.strip()
            if value:
                return value[:500]
    except OSError:
        return ""
    return ""


def es_field_coverage(base: str, index: str, target_ids: list[str]) -> dict:
    root = f"{base.rstrip('/')}/{index}"
    mapping = request_json(root + "/_mapping")
    mapping_root = mapping.get(index, mapping).get("mappings", {})
    properties = mapping_root.get("properties", {})
    count = request_json(root + "/_count").get("count")
    fields = ["title", "file_path", "section_context", "lexical_context"]
    aggregations = {}
    for field in fields:
        aggregations[f"exists_{field}"] = {"filter": {"exists": {"field": field}}}
    aggregate = request_json(
        root + "/_search",
        {"size": 0, "aggs": aggregations},
    ).get("aggregations", {})
    target = request_json(
        root + "/_search",
        {
            "size": 10000,
            "query": {"terms": {"doc_id": target_ids}},
            "_source": ["doc_id", "chunk_id", *fields],
        },
    ).get("hits", {}).get("hits", [])
    target_presence = {}
    for field in fields:
        present = sum(bool(str((hit.get("_source") or {}).get(field) or "").strip()) for hit in target)
        target_presence[field] = {"present_values": present, "target_chunk_hits": len(target)}
    return {
        "base": base,
        "index": index,
        "document_count": count,
        "mapping_fields": sorted(properties),
        "field_mappings": {field: properties.get(field) for field in fields if field in properties},
        "global_field_presence": {
            field: int(aggregate.get(f"exists_{field}", {}).get("doc_count", 0))
            for field in fields
        },
        "target_field_presence": target_presence,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--o0-funnel", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, default=Path("corpus/all_documents"))
    parser.add_argument("--bge-manifest", type=Path, default=Path(".index_cache/full_es_bge_small/manifest.sqlite3"))
    parser.add_argument("--conan-manifest", type=Path, default=Path(".index_cache/full_es_qwen3_emb_v3_conan448/manifest.sqlite3"))
    parser.add_argument("--bge-es", default="http://127.0.0.1:9200")
    parser.add_argument("--conan-es", default="http://10.72.100.29:31920")
    parser.add_argument("--bge-index", default="enterprise-rag-bge-small-v1")
    parser.add_argument("--conan-index", default="enterprise-rag-qwen3-emb-v3-conan448")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    questions = load_jsonl(args.questions)
    funnel = json.loads(args.o0_funnel.read_text(encoding="utf-8"))
    expected = sorted({
        str(value)
        for row in funnel.get("rows", [])
        if row.get("bucket") == "raw_miss" and row.get("expected_document_ids")
        for value in questions.get(str(row["question_id"]), {}).get("expected_doc_ids", [])
        if value
    })
    manifests = {"bge": manifest_rows(args.bge_manifest), "conan": manifest_rows(args.conan_manifest)}
    corpus_files = {}
    for root, _dirs, files in os.walk(args.corpus):
        for name in files:
            if name.endswith(".txt"):
                path = Path(root, name)
                stem = path.stem
                doc_id = stem.split("__", 1)[0]
                corpus_files.setdefault(doc_id, []).append(str(path.relative_to(args.corpus)))

    manifest_summary = {}
    target_rows = []
    for name, rows in manifests.items():
        by_doc = {}
        for row in rows:
            by_doc.setdefault(row["doc_id"], []).append(row)
        manifest_summary[name] = {
            "row_count": len(rows),
            "unique_doc_count": len(by_doc),
            "duplicate_doc_id_count": sum(len(values) > 1 for values in by_doc.values()),
            "missing_file_path_count": sum(not row["file_path"] for row in rows),
            "status_counts": dict(sorted(Counter(row["status"] for row in rows).items())),
            "missing_expected_doc_ids": sorted(set(expected) - set(by_doc)),
        }
        for doc_id in expected:
            row = by_doc.get(doc_id, [{}])[0]
            file_path = row.get("file_path", "")
            corpus_path = args.corpus / file_path if file_path else None
            target_rows.append({
                "model": name,
                "doc_id": doc_id,
                "manifest_file_path": file_path,
                "corpus_file_exists": bool(corpus_path and corpus_path.exists()),
                "filename_title": filename_title(file_path) if file_path else "",
                "first_nonempty_line": first_nonempty_line(corpus_path) if corpus_path and corpus_path.exists() else "",
                "manifest_chunk_count": row.get("chunk_count"),
            })

    output = {
        "schema_version": 1,
        "scope": "O3.9.1 read-only metadata provenance and ES field coverage",
        "expected_raw_miss_doc_count": len(expected),
        "corpus_file_count": sum(len(values) for values in corpus_files.values()),
        "corpus_unique_doc_count": len(corpus_files),
        "manifest_summary": manifest_summary,
        "target_metadata": target_rows,
        "es": {
            "bge": es_field_coverage(args.bge_es, args.bge_index, expected),
            "conan": es_field_coverage(args.conan_es, args.conan_index, expected),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: output[key] for key in ("expected_raw_miss_doc_count", "corpus_file_count", "corpus_unique_doc_count", "manifest_summary", "es")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
