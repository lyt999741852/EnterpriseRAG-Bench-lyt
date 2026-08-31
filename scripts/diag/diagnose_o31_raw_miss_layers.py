"""O3.1 layer diagnosis for effective raw-miss questions.

Separates index coverage, lexical BM25 retrieval, and the dense ranks already
measured by O3. No embedding, generation, reranking, or index mutation is
performed here.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen


def call_json(url: str, payload: dict) -> dict:
    req = Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode())


def load_jsonl(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[str(row["question_id"])] = row
    return rows


def doc_id(hit: dict) -> str:
    source = hit.get("_source") or {}
    chunk = str(source.get("chunk_id") or hit.get("_id", ""))
    return str(source.get("doc_id") or chunk.split("__", 1)[0])


def index_doc_ids(base: str, index: str, expected: list[str]) -> set[str]:
    if not expected:
        return set()
    body = {
        "size": min(100, len(expected)),
        "_source": ["doc_id"],
        "query": {"terms": {"doc_id": expected}},
    }
    hits = call_json(f"{base.rstrip('/')}/{index}/_search", body).get("hits", {}).get("hits", [])
    return {doc_id(hit) for hit in hits}


def bm25_rank(base: str, index: str, question: str, expected: set[str], k: int) -> int | None:
    body = {
        "size": k,
        "_source": ["doc_id", "chunk_id"],
        "query": {"match": {"text": {"query": question, "operator": "or"}}},
    }
    hits = call_json(f"{base.rstrip('/')}/{index}/_search", body).get("hits", {}).get("hits", [])
    for rank, hit in enumerate(hits, 1):
        if doc_id(hit) in expected:
            return rank
    return None


def classify(present: bool, dense_rank: int | None, lexical_rank: int | None) -> str:
    if not present:
        return "index_missing"
    if dense_rank is not None and lexical_rank is not None:
        return "dense_and_lexical"
    if dense_rank is not None:
        return "dense_only"
    if lexical_rank is not None:
        return "lexical_only"
    return "both_miss"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--o0-funnel", type=Path, required=True)
    parser.add_argument("--o3-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bge-es", default="http://127.0.0.1:9200")
    parser.add_argument("--bge-index", default="enterprise-rag-bge-small-v1")
    parser.add_argument("--conan-es", default="http://10.72.100.29:31920")
    parser.add_argument("--conan-index", default="enterprise-rag-qwen3-emb-v3-conan448")
    parser.add_argument("--bm25-k", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    questions = load_jsonl(args.questions)
    funnel = json.loads(args.o0_funnel.read_text(encoding="utf-8"))
    o3 = json.loads(args.o3_output.read_text(encoding="utf-8"))
    raw_rows = [
        row for row in funnel.get("rows", [])
        if row.get("bucket") == "raw_miss" and row.get("expected_document_ids")
    ]
    qids = [str(row["question_id"]) for row in raw_rows if str(row["question_id"]) in questions]
    o3_rows = {str(row["question_id"]): row for row in o3.get("rows", [])}
    qids = [qid for qid in qids if qid in o3_rows]
    expected_by_qid = {
        qid: {str(value) for value in questions[qid].get("expected_doc_ids", []) if value}
        for qid in qids
    }
    all_expected = sorted({value for values in expected_by_qid.values() for value in values})

    presence = {
        "bge": index_doc_ids(args.bge_es, args.bge_index, all_expected),
        "conan": index_doc_ids(args.conan_es, args.conan_index, all_expected),
    }

    def one(qid: str) -> dict:
        expected = expected_by_qid[qid]
        o3_row = o3_rows[qid]
        result = {
            "question_id": qid,
            "question_type": questions[qid].get("question_type"),
            "expected_document_ids": sorted(expected),
        }
        for model_name, base, index in (
            ("bge", args.bge_es, args.bge_index),
            ("conan", args.conan_es, args.conan_index),
        ):
            dense_rank = o3_row[model_name].get("first_expected_rank")
            lexical_rank = bm25_rank(base, index, str(questions[qid]["question"]), expected, args.bm25_k)
            present = bool(expected & presence[model_name])
            result[model_name] = {
                "index_present": present,
                "dense_rank": dense_rank,
                "bm25_rank": lexical_rank,
                "layer": classify(present, dense_rank, lexical_rank),
            }
        return result

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(one, qid): qid for qid in qids}
        for done, future in enumerate(as_completed(futures), 1):
            row = future.result()
            rows.append(row)
            print(
                f"[{done}/{len(qids)}] {row['question_id']}: "
                f"BGE={row['bge']['layer']} Conan={row['conan']['layer']}",
                flush=True,
            )
    rows.sort(key=lambda row: qids.index(row["question_id"]))

    def aggregate(model_name: str, group: list[dict]) -> dict:
        counts: dict[str, int] = {}
        for row in group:
            layer = row[model_name]["layer"]
            counts[layer] = counts.get(layer, 0) + 1
        return {
            "question_count": len(group),
            "layer_counts": dict(sorted(counts.items())),
            "index_present_count": sum(row[model_name]["index_present"] for row in group),
            "dense_hit_count": sum(row[model_name]["dense_rank"] is not None for row in group),
            "bm25_hit_count": sum(row[model_name]["bm25_rank"] is not None for row in group),
        }

    by_type: dict[str, list[dict]] = {}
    for row in rows:
        by_type.setdefault(str(row.get("question_type") or "unknown"), []).append(row)
    output = {
        "schema_version": 1,
        "scope": "O3.1 index presence + BM25 + O3 dense rank on effective raw-miss",
        "question_count": len(rows),
        "expected_document_count": len(all_expected),
        "indices": {
            "bge": {"base": args.bge_es, "index": args.bge_index, "present_expected_document_count": len(presence["bge"])},
            "conan": {"base": args.conan_es, "index": args.conan_index, "present_expected_document_count": len(presence["conan"])},
        },
        "aggregate": {model: aggregate(model, rows) for model in ("bge", "conan")},
        "by_question_type": {
            qtype: {model: aggregate(model, group) for model in ("bge", "conan")}
            for qtype, group in sorted(by_type.items())
        },
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in output.items() if key != "rows"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
