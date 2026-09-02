"""Direct embedding Recall@K screen for the O0 effective raw-miss subset.

The script compares the existing BGE-small ES index with the separate Conan
1792-dim index using the same original question text. It bypasses rewrite,
reranker, PageIndex, generation, and official scoring.
"""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen


def load_jsonl(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[str(row["question_id"])] = row
    return rows


def call_json(url: str, payload: dict | None = None, headers: dict[str, str] | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(
        url,
        data=data,
        method="POST" if payload is not None else "GET",
        headers=headers or {"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode())


def conan_embed(base: str, key: str, texts: list[str]) -> list[list[float]]:
    result = call_json(
        base.rstrip("/") + "/embeddings",
        {"model": "embedding", "input": texts, "encoding_format": "float"},
        {"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    return [row["embedding"] for row in sorted(result["data"], key=lambda row: row.get("index", 0))]


def doc_id(hit: dict) -> str:
    source = hit.get("_source") or {}
    chunk = str(source.get("chunk_id") or hit.get("_id", ""))
    return str(source.get("doc_id") or chunk.split("__", 1)[0])


def retrieve(base: str, index: str, vector: list[float], k: int) -> list[dict]:
    body = {
        "size": k,
        "knn": {
            "field": "embedding",
            "query_vector": vector,
            "k": k,
            "num_candidates": min(10000, max(2 * k, 100)),
        },
        "_source": ["doc_id", "chunk_id"],
    }
    try:
        return call_json(f"{base.rstrip('/')}/{index}/_search", body).get("hits", {}).get("hits", [])
    except Exception:
        fallback = {
            "size": k,
            "_source": ["doc_id", "chunk_id"],
            "query": {
                "script_score": {
                    "query": {"match_all": {}},
                    "script": {
                        "source": "cosineSimilarity(params.q, 'embedding') + 1.0",
                        "params": {"q": vector},
                    },
                }
            },
        }
        return call_json(f"{base.rstrip('/')}/{index}/_search", fallback).get("hits", {}).get("hits", [])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--o0-funnel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bge-es", default="http://127.0.0.1:9200")
    parser.add_argument("--bge-index", default="enterprise-rag-bge-small-v1")
    parser.add_argument("--conan-es", default="http://10.72.100.29:31920")
    parser.add_argument("--conan-index", default="enterprise-rag-qwen3-emb-v3-conan448")
    parser.add_argument("--conan-embedding", default="http://10.72.55.209:7993/v1")
    parser.add_argument("--embedding-key", default=os.environ.get("EMBEDDING_API_KEY", "123456"))
    parser.add_argument("--max-k", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    questions = load_jsonl(args.questions)
    funnel = json.loads(args.o0_funnel.read_text(encoding="utf-8"))
    raw_rows = [
        row for row in funnel.get("rows", [])
        if row.get("bucket") == "raw_miss" and row.get("expected_document_ids")
    ]
    qids = [str(row["question_id"]) for row in raw_rows if str(row["question_id"]) in questions]
    if not qids:
        raise ValueError("no effective raw-miss questions in O0 funnel")

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("BAAI/bge-small-en-v1.5", local_files_only=True)
    texts = [str(questions[qid]["question"]) for qid in qids]
    bge_vectors = model.encode(texts, normalize_embeddings=True, batch_size=32).tolist()
    conan_vectors: list[list[float]] = []
    for start in range(0, len(texts), 16):
        conan_vectors.extend(conan_embed(args.conan_embedding, args.embedding_key, texts[start:start + 16]))
    if len(bge_vectors) != len(conan_vectors):
        raise RuntimeError("embedding batch count mismatch")
    if any(len(vector) != 384 for vector in bge_vectors):
        raise RuntimeError("unexpected BGE-small dimension")
    if any(len(vector) != 1792 for vector in conan_vectors):
        raise RuntimeError("unexpected Conan dimension")

    def one(index: int) -> dict:
        qid = qids[index]
        expected = {str(value) for value in questions[qid].get("expected_doc_ids", []) if value}
        bge_hits = retrieve(args.bge_es, args.bge_index, bge_vectors[index], args.max_k)
        conan_hits = retrieve(args.conan_es, args.conan_index, conan_vectors[index], args.max_k)
        bge_docs = [doc_id(hit) for hit in bge_hits]
        conan_docs = [doc_id(hit) for hit in conan_hits]

        def stats(docs: list[str]) -> dict:
            first_rank = next((rank for rank, value in enumerate(docs, 1) if value in expected), None)
            coverage = {}
            for cutoff in (30, 120, 240, args.max_k):
                visible = set(docs[:cutoff])
                coverage[str(cutoff)] = round(100.0 * len(visible & expected) / len(expected), 2) if expected else None
            return {"first_expected_rank": first_rank, "coverage_pct": coverage, "top30": docs[:30]}

        return {
            "question_id": qid,
            "question_type": questions[qid].get("question_type"),
            "expected_document_ids": sorted(expected),
            "bge": stats(bge_docs),
            "conan": stats(conan_docs),
        }

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(one, index): index for index in range(len(qids))}
        for done, future in enumerate(as_completed(futures), 1):
            row = future.result()
            rows.append(row)
            print(f"[{done}/{len(qids)}] {row['question_id']}: BGE={row['bge']['first_expected_rank']} Conan={row['conan']['first_expected_rank']}", flush=True)
    rows.sort(key=lambda row: qids.index(row["question_id"]))

    def aggregate(group: list[dict], model_name: str) -> dict:
        out = {"question_count": len(group)}
        for cutoff in (30, 120, 240, args.max_k):
            values = [row[model_name]["coverage_pct"][str(cutoff)] for row in group]
            out[f"mean_expected_doc_coverage_at_{cutoff}"] = round(sum(values) / len(values), 2) if values else None
            out[f"question_hit_rate_at_{cutoff}"] = round(100.0 * sum(value > 0 for value in values) / len(values), 2) if values else None
        return out

    by_type: dict[str, list[dict]] = {}
    for row in rows:
        by_type.setdefault(str(row.get("question_type") or "unknown"), []).append(row)
    output = {
        "schema_version": 1,
        "scope": "O3 direct BGE-small vs Conan recall screen on O0 effective raw-miss",
        "question_count": len(rows),
        "dimensions": {"bge": 384, "conan": 1792},
        "aggregate": {
            "bge": aggregate(rows, "bge"),
            "conan": aggregate(rows, "conan"),
        },
        "by_question_type": {
            qtype: {"bge": aggregate(group, "bge"), "conan": aggregate(group, "conan")}
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
