"""S2 offline probe: document-level aggregation and header-first retrieval.

Only question text is sent to Elasticsearch.  Gold ids are used after retrieval
for evaluation, never for query construction.  The probe keeps dense/BM25
chunk retrieval separate, adds a generic first-chunk preference lane, and
aggregates rank evidence by doc_id before evaluating document candidates.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def call_json(url: str, payload: dict) -> dict:
    req = Request(url, data=json.dumps(payload).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode())


def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    return {str(r["question_id"]): r for r in (json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()) if r.get("question_id")}


def source_doc(hit: dict[str, Any]) -> str:
    src = hit.get("_source") or {}
    return str(src.get("doc_id") or src.get("chunk_id") or hit.get("_id", "")).split("__", 1)[0]


def lane_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"doc_id": source_doc(h), "chunk_id": str((h.get("_source") or {}).get("chunk_id") or h.get("_id", "")), "chunk_index": int((h.get("_source") or {}).get("chunk_index") or 0), "score": float(h.get("_score") or 0.0)} for h in hits]


def aggregate_docs(lanes: dict[str, list[dict[str, Any]]], header_weight: float, chunk_bonus: float) -> list[str]:
    scores: dict[str, float] = {}
    counts: dict[str, int] = {}
    header_seen: set[str] = set()
    for lane_name, hits in lanes.items():
        lane_weight = header_weight if lane_name.startswith("header_") else 1.0
        for rank, hit in enumerate(hits, 1):
            doc = hit["doc_id"]
            if not doc:
                continue
            contribution = lane_weight / (60.0 + rank)
            scores[doc] = scores.get(doc, 0.0) + contribution
            counts[doc] = counts.get(doc, 0) + 1
            if hit["chunk_index"] == 0:
                header_seen.add(doc)
    for doc, count in counts.items():
        scores[doc] += chunk_bonus * math.log1p(min(count, 8))
        if doc in header_seen:
            scores[doc] += chunk_bonus
    return [doc for doc, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))]


def stats(values: list[str], expected: set[str], cutoffs: tuple[int, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in cutoffs:
        found = set(values[:k]) & expected
        out[str(k)] = {"hit": bool(found), "expected_found": len(found), "expected_total": len(expected), "coverage_pct": round(100 * len(found) / len(expected), 2) if expected else None}
    out["first_expected_rank"] = next((i for i, v in enumerate(values, 1) if v in expected), None)
    return out


def aggregate(rows: list[dict[str, Any]], field: str, cutoffs: tuple[int, ...]) -> dict[str, Any]:
    out = {"question_count": len(rows)}
    for k in cutoffs:
        vals = [r[field][str(k)]["hit"] for r in rows]
        cov = [r[field][str(k)]["coverage_pct"] for r in rows if r[field][str(k)]["coverage_pct"] is not None]
        out[f"hit_rate_at_{k}"] = round(100 * sum(vals) / len(vals), 2) if vals else None
        out[f"mean_coverage_at_{k}"] = round(sum(cov) / len(cov), 2) if cov else None
    ranks = [r[field]["first_expected_rank"] for r in rows if r[field]["first_expected_rank"] is not None]
    out["ranked_question_count"] = len(ranks)
    out["mean_first_expected_rank"] = round(sum(ranks) / len(ranks), 2) if ranks else None
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", type=Path, required=True)
    ap.add_argument("--o0-funnel", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--es", default="http://127.0.0.1:9200")
    ap.add_argument("--index", default="enterprise-rag-bge-small-v1")
    ap.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()
    questions = load_jsonl(args.questions)
    funnel = json.loads(args.o0_funnel.read_text(encoding="utf-8"))
    effective = [str(r["question_id"]) for r in funnel.get("rows", []) if r.get("expected_document_ids") and str(r.get("question_id")) in questions]
    semantic = {qid for qid in effective if questions[qid].get("question_type") == "semantic"}
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(args.model, local_files_only=True)
    vectors = model.encode([str(questions[qid]["question"]) for qid in effective], normalize_embeddings=True, batch_size=32, show_progress_bar=False).tolist()
    vector_by_id = dict(zip(effective, vectors))
    cutoffs = (10, 20, 30)

    def one(qid: str) -> dict[str, Any]:
        question = str(questions[qid]["question"])
        expected = {str(x) for x in questions[qid].get("expected_doc_ids", []) if x}
        url = f"{args.es.rstrip('/')}/{args.index}/_search"
        dense_body = {"size": 500, "knn": {"field": "embedding", "query_vector": vector_by_id[qid], "k": 500, "num_candidates": 1000}, "_source": ["doc_id", "chunk_id", "chunk_index"]}
        bm25_body = {"size": 500, "query": {"match": {"text": {"query": question}}}, "_source": ["doc_id", "chunk_id", "chunk_index"]}
        header_bm25_body = {"size": 500, "query": {"function_score": {"query": {"match": {"text": {"query": question}}}, "functions": [{"filter": {"term": {"chunk_index": 0}}, "weight": 3.0}], "score_mode": "sum", "boost_mode": "sum"}}, "_source": ["doc_id", "chunk_id", "chunk_index"]}
        started = time.perf_counter()
        dense = lane_hits(call_json(url, dense_body).get("hits", {}).get("hits", []))
        bm25 = lane_hits(call_json(url, bm25_body).get("hits", {}).get("hits", []))
        header_bm25 = lane_hits(call_json(url, header_bm25_body).get("hits", {}).get("hits", []))
        header_dense: list[dict[str, Any]] = []
        header_error = ""
        try:
            header_dense_body = {"size": 500, "knn": {"field": "embedding", "query_vector": vector_by_id[qid], "k": 500, "num_candidates": 1000, "filter": {"term": {"chunk_index": 0}}}, "_source": ["doc_id", "chunk_id", "chunk_index"]}
            header_dense = lane_hits(call_json(url, header_dense_body).get("hits", {}).get("hits", []))
        except (HTTPError, OSError) as exc:
            header_error = str(exc)
        lanes = {"dense": dense, "bm25": bm25, "header_bm25": header_bm25, "header_dense": header_dense}
        base_doc = aggregate_docs({"dense": dense, "bm25": bm25}, 0.0, 0.0)
        header_doc = aggregate_docs(lanes, 0.65, 0.08)
        header_strong_doc = aggregate_docs(lanes, 1.0, 0.16)
        latency = round((time.perf_counter() - started) * 1000, 2)
        return {"question_id": qid, "question_type": questions[qid].get("question_type"), "expected_document_ids": sorted(expected), "base_document": stats(base_doc, expected, cutoffs), "header_document": stats(header_doc, expected, cutoffs), "header_strong_document": stats(header_strong_doc, expected, cutoffs), "header_dense_error": header_error, "latency_ms": latency, "gold_header_hit": any(h["doc_id"] in expected for h in header_dense + header_bm25), "gold_base_hit": any(h["doc_id"] in expected for h in dense + bm25), "gold_header_chunk": next((h["chunk_id"] for h in header_dense + header_bm25 if h["doc_id"] in expected), None)}

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(one, qid): qid for qid in effective}
        for i, fut in enumerate(as_completed(futures), 1):
            rows.append(fut.result())
            if i % 25 == 0 or i == len(effective): print(f"[{i}/{len(effective)}]", flush=True)
    rows.sort(key=lambda r: effective.index(r["question_id"]))
    groups = {"semantic": [r for r in rows if r["question_id"] in semantic], "controls": [r for r in rows if r["question_id"] not in semantic], "effective": rows}
    report = {"schema_version": 1, "scope": "S2 document-level aggregation and header-first retrieval", "index": args.index, "model": args.model, "effective_question_count": len(rows), "semantic_question_count": len(semantic), "cutoffs": list(cutoffs), "groups": {name: {"question_count": len(group), "base_document": aggregate(group, "base_document", cutoffs), "header_document": aggregate(group, "header_document", cutoffs), "header_strong_document": aggregate(group, "header_strong_document", cutoffs), "header_gold_hit_count": sum(r["gold_header_hit"] for r in group), "base_gold_hit_count": sum(r["gold_base_hit"] for r in group), "mean_latency_ms": round(statistics.mean(r["latency_ms"] for r in group), 2) if group else None} for name, group in groups.items()}, "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["groups"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
