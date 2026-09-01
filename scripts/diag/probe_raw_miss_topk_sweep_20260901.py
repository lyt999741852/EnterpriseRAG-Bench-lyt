"""Probe original BGE dense/BM25 Recall at wider pre-rerank cutoffs.

Read-only ES queries against the production BGE-small index.  The same
question embedding is used for every cutoff; dense and BM25 are fetched once
at max-k and evaluated at 30/120/240/500.  Results are reported for the O0
effective raw-miss subset and for all effective questions as a control.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


def call_json(url: str, payload: dict) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode())


def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    return {
        str(row["question_id"]): row
        for row in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
        if row.get("question_id")
    }


def source_doc(hit: dict[str, Any]) -> str:
    source = hit.get("_source") or {}
    value = source.get("doc_id")
    if value:
        return str(value)
    return str(source.get("chunk_id") or hit.get("_id", "")).split("__", 1)[0]


def hit_stats(values: list[str], expected: set[str], cutoffs: tuple[int, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for cutoff in cutoffs:
        found = set(values[:cutoff]) & expected
        result[str(cutoff)] = {
            "hit": bool(found),
            "expected_found": len(found),
            "expected_total": len(expected),
            "coverage_pct": round(100.0 * len(found) / len(expected), 2) if expected else None,
        }
    first = next((rank for rank, value in enumerate(values, 1) if value in expected), None)
    result["first_expected_rank"] = first
    return result


def union_stats(
    dense: list[str], bm25: list[str], expected: set[str], cutoffs: tuple[int, ...]
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for cutoff in cutoffs:
        found = (set(dense[:cutoff]) | set(bm25[:cutoff])) & expected
        result[str(cutoff)] = {
            "hit": bool(found),
            "expected_found": len(found),
            "expected_total": len(expected),
            "coverage_pct": round(100.0 * len(found) / len(expected), 2) if expected else None,
        }
    ranks: list[int] = []
    for cutoff in cutoffs:
        found = (set(dense[:cutoff]) | set(bm25[:cutoff])) & expected
        if found:
            ranks.append(cutoff)
            break
    result["first_expected_rank"] = ranks[0] if ranks else None
    return result


def aggregate(rows: list[dict[str, Any]], key: str, cutoffs: tuple[int, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {"question_count": len(rows)}
    for cutoff in cutoffs:
        values = [row[key][str(cutoff)]["hit"] for row in rows]
        result[f"hit_rate_at_{cutoff}"] = round(100.0 * sum(values) / len(values), 2) if values else None
        coverage = [row[key][str(cutoff)]["coverage_pct"] for row in rows if row[key][str(cutoff)]["coverage_pct"] is not None]
        result[f"mean_coverage_at_{cutoff}"] = round(sum(coverage) / len(coverage), 2) if coverage else None
    ranks = [row[key]["first_expected_rank"] for row in rows if row[key]["first_expected_rank"] is not None]
    result["ranked_question_count"] = len(ranks)
    result["mean_first_expected_rank"] = round(sum(ranks) / len(ranks), 2) if ranks else None
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--o0-funnel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--es", default="http://127.0.0.1:9200")
    parser.add_argument("--index", default="enterprise-rag-bge-small-v1")
    parser.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    parser.add_argument("--metadata-fields", action="store_true", help="search shadow metadata fields in addition to text")
    parser.add_argument("--metadata-mode", choices=("best_fields", "bool_should", "append_union"), default="best_fields", help="metadata query composition when --metadata-fields is set")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    questions = load_jsonl(args.questions)
    funnel = json.loads(args.o0_funnel.read_text(encoding="utf-8"))
    funnel_rows = {str(row["question_id"]): row for row in funnel.get("rows", [])}
    raw_ids = sorted(
        qid for qid, row in funnel_rows.items()
        if row.get("bucket") == "raw_miss"
        and row.get("expected_document_ids")
        and qid in questions
    )
    effective_ids = sorted(
        qid for qid, row in funnel_rows.items()
        if row.get("expected_document_ids") and qid in questions
    )
    if not raw_ids:
        raise ValueError("no effective raw-miss rows")

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(args.model, local_files_only=True)
    vectors = model.encode(
        [str(questions[qid]["question"]) for qid in effective_ids],
        normalize_embeddings=True,
        batch_size=32,
        show_progress_bar=False,
    ).tolist()
    vector_by_id = dict(zip(effective_ids, vectors))
    cutoffs = (30, 120, 240, 500)

    def one(qid: str) -> dict[str, Any]:
        question = str(questions[qid]["question"])
        expected = {str(value) for value in questions[qid].get("expected_doc_ids", []) if value}
        dense_body = {
            "size": max(cutoffs),
            "knn": {
                "field": "embedding",
                "query_vector": vector_by_id[qid],
                "k": max(cutoffs),
                "num_candidates": min(10000, max(2 * max(cutoffs), 100)),
            },
            "_source": ["doc_id", "chunk_id"],
        }
        bm25_query = {"match": {"text": {"query": question, "operator": "or"}}}
        if args.metadata_fields and args.metadata_mode != "append_union":
            if args.metadata_mode == "bool_should":
                bm25_query = {"bool": {"should": [
                    {"match": {"text": {"query": question, "operator": "or"}}},
                    {"match": {"lexical_context": {"query": question, "operator": "or", "boost": 0.35}}},
                    {"match": {"title": {"query": question, "operator": "or", "boost": 1.5}}},
                    {"match": {"file_path": {"query": question, "operator": "or", "boost": 0.5}}},
                ], "minimum_should_match": 1}}
            else:
                bm25_query = {"multi_match": {"query": question, "fields": ["text", "lexical_context^2", "title^2", "file_path"], "type": "best_fields", "operator": "or"}}
        bm25_body = {
            "size": max(cutoffs),
            "query": bm25_query,
            "_source": ["doc_id", "chunk_id"],
        }
        started = time.perf_counter()
        dense_hits = call_json(f"{args.es.rstrip('/')}/{args.index}/_search", dense_body).get("hits", {}).get("hits", [])
        dense_ms = round((time.perf_counter() - started) * 1000, 2)
        started = time.perf_counter()
        bm25_hits = call_json(f"{args.es.rstrip('/')}/{args.index}/_search", bm25_body).get("hits", {}).get("hits", [])
        if args.metadata_fields and args.metadata_mode == "append_union":
            metadata_body = {
                "size": max(cutoffs),
                "query": {"multi_match": {"query": question, "fields": ["lexical_context^2", "title^2", "file_path"], "type": "best_fields", "operator": "or"}},
                "_source": ["doc_id", "chunk_id"],
            }
            metadata_hits = call_json(f"{args.es.rstrip('/')}/{args.index}/_search", metadata_body).get("hits", {}).get("hits", [])
            seen = {hit.get("_id") for hit in bm25_hits}
            bm25_hits.extend(hit for hit in metadata_hits if hit.get("_id") not in seen and not seen.add(hit.get("_id")))
        bm25_ms = round((time.perf_counter() - started) * 1000, 2)
        dense = [source_doc(hit) for hit in dense_hits]
        bm25 = [source_doc(hit) for hit in bm25_hits]
        return {
            "question_id": qid,
            "question_type": questions[qid].get("question_type"),
            "expected_document_ids": sorted(expected),
            "dense": hit_stats(dense, expected, cutoffs),
            "bm25": hit_stats(bm25, expected, cutoffs),
            "union": union_stats(dense, bm25, expected, cutoffs),
            "dense_latency_ms": dense_ms,
            "bm25_latency_ms": bm25_ms,
        }

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(one, qid): qid for qid in effective_ids}
        for done, future in enumerate(as_completed(futures), 1):
            rows.append(future.result())
            if done % 25 == 0 or done == len(effective_ids):
                print(f"[{done}/{len(effective_ids)}]", flush=True)
    rows.sort(key=lambda row: effective_ids.index(row["question_id"]))
    raw_set = set(raw_ids)

    def make_group(group: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "question_count": len(group),
            "dense": aggregate(group, "dense", cutoffs),
            "bm25": aggregate(group, "bm25", cutoffs),
            "union": aggregate(group, "union", cutoffs),
            "mean_dense_latency_ms": round(statistics.mean(row["dense_latency_ms"] for row in group), 2) if group else None,
            "mean_bm25_latency_ms": round(statistics.mean(row["bm25_latency_ms"] for row in group), 2) if group else None,
        }

    raw_rows = [row for row in rows if row["question_id"] in raw_set]
    by_type: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_type.setdefault(str(row.get("question_type") or "unknown"), []).append(row)
    report = {
        "schema_version": 1,
        "scope": "read-only production BGE top-k sweep for O0 raw-miss and effective controls",
        "index": args.index,
        "model": args.model,
        "effective_question_count": len(rows),
        "raw_miss_count": len(raw_rows),
        "cutoffs": list(cutoffs),
        "raw_miss": make_group(raw_rows),
        "effective": make_group(rows),
        "by_question_type": {key: make_group(value) for key, value in sorted(by_type.items())},
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("effective_question_count", "raw_miss_count", "cutoffs", "raw_miss", "effective")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
