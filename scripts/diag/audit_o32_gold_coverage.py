"""O3.2 read-only audit of gold document coverage across corpus/manifests/ES."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from collections import Counter
from pathlib import Path
from urllib.request import Request, urlopen


def load_jsonl(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[str(row["question_id"])] = row
    return rows


def manifest_rows(path: Path, doc_ids: list[str]) -> tuple[dict[str, list[dict]], dict[str, str]]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        metadata = {str(k): str(v) for k, v in con.execute("SELECT key,value FROM metadata")}
        if not doc_ids:
            return {}, metadata
        marks = ",".join("?" for _ in doc_ids)
        rows = con.execute(
            f"SELECT file_path,doc_id,source_type,status,chunk_count,error_message "
            f"FROM documents WHERE doc_id IN ({marks})",
            doc_ids,
        ).fetchall()
        grouped: dict[str, list[dict]] = {}
        for file_path, doc_id, source_type, status, chunk_count, error_message in rows:
            grouped.setdefault(str(doc_id), []).append(
                {
                    "file_path": file_path,
                    "source_type": source_type,
                    "status": status,
                    "chunk_count": chunk_count,
                    "error_message": error_message,
                }
            )
        return grouped, metadata
    finally:
        con.close()


def corpus_matches(corpus: Path, expected: set[str]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {doc_id: [] for doc_id in expected}
    for root, _dirs, files in os.walk(corpus):
        for name in files:
            if not name.endswith(".txt"):
                continue
            doc_id = name.rsplit(".", 1)[0].split("__", 1)[0]
            if doc_id in found:
                found[doc_id].append(str(Path(root, name).relative_to(corpus)))
    return found


def index_matches(base: str, index: str, expected: list[str]) -> set[str]:
    if not expected:
        return set()
    body = {
        "size": min(100, len(expected)),
        "_source": ["doc_id"],
        "query": {"terms": {"doc_id": expected}},
    }
    req = Request(
        f"{base.rstrip('/')}/{index}/_search",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=180) as response:
        payload = json.loads(response.read().decode())
    hits = payload.get("hits", {}).get("hits", [])
    return {
        str((hit.get("_source") or {}).get("doc_id"))
        for hit in hits
        if (hit.get("_source") or {}).get("doc_id")
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--o0-funnel", type=Path, required=True)
    parser.add_argument("--o31-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, default=Path("corpus/all_documents"))
    parser.add_argument("--bge-manifest", type=Path, default=Path(".index_cache/full_es_bge_small/manifest.sqlite3"))
    parser.add_argument("--conan-manifest", type=Path, default=Path(".index_cache/full_es_qwen3_emb_v3_conan448/manifest.sqlite3"))
    parser.add_argument("--bge-es", default="http://127.0.0.1:9200")
    parser.add_argument("--bge-index", default="enterprise-rag-bge-small-v1")
    parser.add_argument("--conan-es", default="http://10.72.100.29:31920")
    parser.add_argument("--conan-index", default="enterprise-rag-qwen3-emb-v3-conan448")
    args = parser.parse_args()

    questions = load_jsonl(args.questions)
    funnel = json.loads(args.o0_funnel.read_text(encoding="utf-8"))
    o31 = json.loads(args.o31_output.read_text(encoding="utf-8"))
    raw = [
        row for row in funnel.get("rows", [])
        if row.get("bucket") == "raw_miss" and row.get("expected_document_ids")
    ]
    qids = [str(row["question_id"]) for row in raw if str(row["question_id"]) in questions]
    expected_by_qid = {
        qid: {str(value) for value in questions[qid].get("expected_doc_ids", []) if value}
        for qid in qids
    }
    expected = sorted({value for values in expected_by_qid.values() for value in values})
    corpus = corpus_matches(args.corpus, set(expected))
    manifests = {}
    metadata = {}
    for name, path in (("bge", args.bge_manifest), ("conan", args.conan_manifest)):
        manifests[name], metadata[name] = manifest_rows(path, expected)
    index_ids = {
        "bge": index_matches(args.bge_es, args.bge_index, expected),
        "conan": index_matches(args.conan_es, args.conan_index, expected),
    }
    o31_rows = {str(row["question_id"]): row for row in o31.get("rows", [])}

    # Index presence is already measured per question by O3.1; this audit focuses
    # on the upstream corpus and manifest provenance.
    doc_rows = []
    for doc_id in expected:
        item = {"doc_id": doc_id, "corpus_files": corpus.get(doc_id, [])}
        for model in ("bge", "conan"):
            rows = manifests[model].get(doc_id, [])
            item[model] = {
                "manifest_rows": rows,
                "manifest_statuses": sorted({str(row["status"]) for row in rows}),
                "index_present": doc_id in index_ids[model],
            }
        doc_rows.append(item)

    def question_layer(qid: str, model: str) -> str:
        return str(o31_rows.get(qid, {}).get(model, {}).get("layer", "missing_o31"))

    def aggregate(model: str) -> dict:
        layers = Counter(question_layer(qid, model) for qid in qids)
        corpus_missing = sum(not any(corpus.get(doc_id) for doc_id in expected_by_qid[qid]) for qid in qids)
        manifest_missing = sum(
            not any(manifests[model].get(doc_id) for doc_id in expected_by_qid[qid]) for qid in qids
        )
        return {
            "question_count": len(qids),
            "o31_layer_counts": dict(sorted(layers.items())),
            "questions_without_any_corpus_file": corpus_missing,
            "questions_without_any_manifest_row": manifest_missing,
            "manifest_doc_count": len(manifests[model]),
            "index_doc_count": len(index_ids[model]),
            "index_missing_doc_ids": sorted(set(expected) - index_ids[model]),
            "manifest_status_counts_for_expected_docs": dict(
                sorted(Counter(status for doc_id in expected for status in {row["status"] for row in manifests[model].get(doc_id, [])}).items())
            ),
        }

    output = {
        "schema_version": 1,
        "scope": "O3.2 gold coverage audit on O0 effective raw-miss",
        "question_count": len(qids),
        "expected_document_count": len(expected),
        "paths": {
            "corpus": str(args.corpus),
            "bge_manifest": str(args.bge_manifest),
            "conan_manifest": str(args.conan_manifest),
            "bge_index": f"{args.bge_es}/{args.bge_index}",
            "conan_index": f"{args.conan_es}/{args.conan_index}",
        },
        "metadata": metadata,
        "aggregate": {model: aggregate(model) for model in ("bge", "conan")},
        "documents": doc_rows,
        "questions": [
            {
                "question_id": qid,
                "question_type": questions[qid].get("question_type"),
                "expected_document_ids": sorted(expected_by_qid[qid]),
                "bge_layer": question_layer(qid, "bge"),
                "conan_layer": question_layer(qid, "conan"),
            }
            for qid in qids
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in output.items() if key not in {"documents", "questions"}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
