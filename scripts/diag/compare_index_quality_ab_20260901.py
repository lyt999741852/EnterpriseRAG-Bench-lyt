"""Compare dense/BM25 ranking in the isolated index-quality A/B indices."""

from __future__ import annotations

import argparse
import json
import time
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


def doc_id(hit: dict) -> str:
    source = hit.get("_source") or {}
    return str(source.get("doc_id") or str(source.get("chunk_id") or hit.get("_id", "")).split("__", 1)[0])


def dense_hits(base: str, index: str, vector: list[float], k: int) -> list[dict]:
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


def bm25_hits(base: str, index: str, question: str, k: int) -> list[dict]:
    body = {
        "size": k,
        "query": {"match": {"text": {"query": question, "operator": "or"}}},
        "_source": ["doc_id", "chunk_id"],
    }
    return call_json(f"{base.rstrip('/')}/{index}/_search", body).get("hits", {}).get("hits", [])


def load_questions(path: Path, funnel_path: Path) -> tuple[list[str], dict[str, dict]]:
    questions = {
        str(row["question_id"]): row
        for row in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    }
    funnel = json.loads(funnel_path.read_text(encoding="utf-8"))
    qids = [
        str(row["question_id"])
        for row in funnel.get("rows", [])
        if row.get("bucket") == "raw_miss"
        and row.get("expected_document_ids")
        and str(row["question_id"]) in questions
    ]
    return qids, questions


def stats(documents: list[str], expected: set[str]) -> dict:
    first = next((rank for rank, value in enumerate(documents, 1) if value in expected), None)
    coverage = {
        str(k): round(100.0 * len(set(documents[:k]) & expected) / len(expected), 2)
        if expected else None
        for k in (30, 120, 240, 1000)
    }
    return {
        "first_expected_rank": first,
        "coverage_pct": coverage,
        "hit_at": {str(k): bool(set(documents[:k]) & expected) for k in (30, 120, 240, 1000)},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--o0-funnel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--es", default="http://127.0.0.1:9200")
    parser.add_argument("--index-a", default="o34_quality_a_bge_small_20260831")
    parser.add_argument("--index-b", default="o34_quality_b_bge_small_20260831")
    parser.add_argument("--k", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    qids, questions = load_questions(args.questions, args.o0_funnel)
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("BAAI/bge-small-en-v1.5", local_files_only=True)
    vectors = model.encode(
        [str(questions[qid]["question"]) for qid in qids],
        normalize_embeddings=True,
        batch_size=32,
    ).tolist()

    def one(position: int) -> dict:
        qid = qids[position]
        expected = {str(value) for value in questions[qid].get("expected_doc_ids", []) if value}
        result = {
            "question_id": qid,
            "question_type": questions[qid].get("question_type"),
            "expected_document_ids": sorted(expected),
        }
        for variant, index in (("a", args.index_a), ("b", args.index_b)):
            started = time.perf_counter()
            dense = [doc_id(hit) for hit in dense_hits(args.es, index, vectors[position], args.k)]
            dense_ms = round((time.perf_counter() - started) * 1000, 2)
            started = time.perf_counter()
            lexical = [doc_id(hit) for hit in bm25_hits(args.es, index, str(questions[qid]["question"]), args.k)]
            lexical_ms = round((time.perf_counter() - started) * 1000, 2)
            result[variant] = {
                "dense": stats(dense, expected),
                "bm25": stats(lexical, expected),
                "dense_latency_ms": dense_ms,
                "bm25_latency_ms": lexical_ms,
            }
        return result

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(one, position): position for position in range(len(qids))}
        for done, future in enumerate(as_completed(futures), 1):
            row = future.result()
            rows.append(row)
            print(f"[{done}/{len(qids)}] {row['question_id']}", flush=True)
    rows.sort(key=lambda row: qids.index(row["question_id"]))

    def aggregate(group: list[dict], variant: str, method: str) -> dict:
        values = [row[variant][method] for row in group]
        return {
            "question_count": len(values),
            "mean_expected_doc_coverage": {
                str(k): round(sum(v["coverage_pct"][str(k)] for v in values) / len(values), 2)
                for k in (30, 120, 240, 1000)
            },
            "question_hit_rate": {
                str(k): round(100.0 * sum(v["hit_at"][str(k)] for v in values) / len(values), 2)
                for k in (30, 120, 240, 1000)
            },
            "mean_first_expected_rank": round(
                sum(v["first_expected_rank"] or (args.k + 1) for v in values) / len(values), 2
            ),
            "mean_latency_ms": round(sum(row[variant][f"{method}_latency_ms"] for row in group) / len(group), 2),
        }

    by_type: dict[str, list[dict]] = {}
    for row in rows:
        by_type.setdefault(str(row.get("question_type") or "unknown"), []).append(row)
    output = {
        "schema_version": 1,
        "scope": "isolated A/B dense and BM25 ranking on O0 effective raw-miss",
        "question_count": len(rows),
        "expected_document_count": len({doc for row in rows for doc in row["expected_document_ids"]}),
        "indices": {"a": args.index_a, "b": args.index_b},
        "aggregate": {
            variant: {
                method: aggregate(rows, variant, method)
                for method in ("dense", "bm25")
            }
            for variant in ("a", "b")
        },
        "by_question_type": {
            qtype: {
                variant: {method: aggregate(group, variant, method) for method in ("dense", "bm25")}
                for variant in ("a", "b")
            }
            for qtype, group in sorted(by_type.items())
        },
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in output.items() if key not in {"rows", "by_question_type"}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
