"""Fast full500 retrieval: fixed four hybrid views, RRF Top-500, no routing.

This is the throughput-safe companion to the S3 baseline.  It deliberately
avoids the per-question LLM facet planner while preserving the proven generic
four-lane strategy.  The report schema is compatible with the document-aware
generation runner: the RRF Top-500 pool is retained as an append-only reserve,
and the first 30 items are the relevance-ordered admission seed.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = str(Path(__file__).resolve().parents[2])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.elasticsearch_backend import ElasticsearchBackend, ElasticsearchConfig, ElasticsearchRetriever
from src.embedder import EmbedderConfig, create_embedder
from scripts.diag.run_s3_no_pageindex_agentic_20260902 import aggregate, doc_recall, load_jsonl, rrf_merge, views


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", type=Path, required=True)
    ap.add_argument("--ids-file", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--es", default="http://127.0.0.1:9200")
    ap.add_argument("--index", default="enterprise-rag-bge-small-v1")
    ap.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    args = ap.parse_args()

    all_questions = load_jsonl(args.questions)
    qids = [x.strip() for x in args.ids_file.read_text(encoding="utf-8").splitlines() if x.strip()]
    questions = {qid: all_questions[qid] for qid in qids}
    if len(questions) != len(qids):
        raise ValueError("question id missing from questions.jsonl")

    embedder = create_embedder(EmbedderConfig(
        provider="sentence_transformers", model_name=args.model, device="cpu",
        batch_size=64, dimension=384, revision="5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
    ))
    backend = ElasticsearchBackend(ElasticsearchConfig(
        url=args.es, index_name=args.index, alias_name="enterprise-rag-bge-small", request_timeout=180,
    ))
    retriever = ElasticsearchRetriever(backend, embedder, top_k=500, candidate_k=500, rrf_k=60)
    embed_lock = threading.Lock()
    cutoffs = (30, 120, 240, 500)

    def retrieve(text: str) -> list[Any]:
        with embed_lock:
            return retriever.retrieve_hybrid(text, dense_weight=0.3)

    def one(qid: str) -> dict[str, Any]:
        q = questions[qid]
        question = str(q["question"])
        expected = {str(x) for x in q.get("expected_doc_ids", []) if x}
        started = time.perf_counter()
        lane_text = views(question)
        lane_results = {name: retrieve(text) for name, text in lane_text.items()}
        pool = rrf_merge(
            [(lane_results[name], weight) for name, weight in
             (("original", 1.2), ("lexical", 1.0), ("semantic", 0.9), ("facet", 0.4))],
            500,
        )
        # Rerank inference is intentionally not called here: the endpoint has
        # been observed to hang.  RRF order is retained as a deterministic,
        # fail-open relevance order and recorded explicitly in the report.
        final = pool[:30]
        return {
            "question_id": qid,
            "question_type": q.get("question_type"),
            "expected_document_ids": sorted(expected),
            "lane_counts": {name: len(values) for name, values in lane_results.items()},
            "augmented_pre_rerank_recall": doc_recall(pool, expected, cutoffs),
            "augmented_recall": doc_recall(final, expected, cutoffs),
            "augmented_pre_rerank_chunk_ids": [x.chunk_id for x in pool],
            "augmented_candidate_chunk_ids": [x.chunk_id for x in final],
            "rerank_status": "bypassed_rerank_endpoint_fail_open",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(one, qid): qid for qid in qids}
        for i, future in enumerate(as_completed(futures), 1):
            rows.append(future.result())
            print(f"[{i}/{len(qids)}]", flush=True)
    rows.sort(key=lambda row: qids.index(row["question_id"]))
    groups = {
        "all": rows,
        "semantic": [r for r in rows if r["question_type"] == "semantic"],
        "controls": [r for r in rows if r["question_type"] != "semantic"],
    }
    report = {
        "schema_version": 3,
        "scope": "S4 fast fixed four-lane hybrid Top-500 + doc-aware generation",
        "question_count": len(rows), "retrieval_top_k": 500, "rrf_pool_k": 500,
        "rerank_status": "bypassed_rerank_endpoint_fail_open",
        "groups": {
            name: {
                "question_count": len(group),
                "pre_rerank": aggregate(group, "augmented_pre_rerank_recall", cutoffs),
                "candidate": aggregate(group, "augmented_recall", cutoffs),
                "mean_latency_ms": round(statistics.mean(r["latency_ms"] for r in group), 2) if group else 0.0,
            }
            for name, group in groups.items()
        },
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["groups"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
