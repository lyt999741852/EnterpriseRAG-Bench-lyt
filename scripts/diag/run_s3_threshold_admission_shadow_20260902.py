"""S3 threshold-admission shadow test over the fixed AB50 set.

Retrieves the same four lanes as S3, reranks the 120-item base pool, and
compares rank caps and per-query relative-score admission policies without
calling the generator.  This isolates candidate admission from answer quality.
"""
from __future__ import annotations

import argparse
import json
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.elasticsearch_backend import ElasticsearchBackend, ElasticsearchConfig, ElasticsearchRetriever
from src.embedder import EmbedderConfig, create_embedder

from run_s3_no_pageindex_agentic_20260902 import load_jsonl, rrf_merge, tokenize, views


def recall(values: list[Any], expected: set[str]) -> dict[str, Any]:
    docs: list[str] = []
    seen: set[str] = set()
    for item in values:
        if item.doc_id and item.doc_id not in seen:
            seen.add(item.doc_id)
            docs.append(item.doc_id)
    found = set(docs) & expected
    return {
        "hit": bool(found),
        "expected_found": len(found),
        "expected_total": len(expected),
        "coverage_pct": round(100 * len(found) / len(expected), 2) if expected else None,
        "first_expected_rank": next((i for i, d in enumerate(docs, 1) if d in expected), None),
    }


def aggregate(rows: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    vals = [r["variants"][variant] for r in rows]
    coverages = [v["coverage_pct"] for v in vals if v["coverage_pct"] is not None]
    return {
        "question_count": len(vals),
        "hit_rate": round(100 * sum(v["hit"] for v in vals) / len(vals), 2) if vals else None,
        "mean_expected_doc_coverage": round(statistics.mean(coverages), 2) if coverages else None,
        "ranked_question_count": sum(v["first_expected_rank"] is not None for v in vals),
        "mean_chunks": round(statistics.mean(v["chunk_count"] for v in vals), 2) if vals else None,
        "mean_docs": round(statistics.mean(v["doc_count"] for v in vals), 2) if vals else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", type=Path, required=True)
    ap.add_argument("--ids-file", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--es", default="http://127.0.0.1:9200")
    ap.add_argument("--index", default="enterprise-rag-bge-small-v1")
    ap.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    ap.add_argument("--rerank-base", default="http://10.72.55.209:7992/v1")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    all_questions = load_jsonl(args.questions)
    qids = [x.strip() for x in args.ids_file.read_text(encoding="utf-8").splitlines() if x.strip()]
    questions = {qid: all_questions[qid] for qid in qids}
    embedder = create_embedder(EmbedderConfig(provider="sentence_transformers", model_name=args.model, device="cpu", batch_size=64, dimension=384, revision="5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"))
    backend = ElasticsearchBackend(ElasticsearchConfig(url=args.es, index_name=args.index, alias_name="enterprise-rag-bge-small", request_timeout=180))
    retriever = ElasticsearchRetriever(backend, embedder, top_k=120, candidate_k=500, rrf_k=60)
    embed_lock = threading.Lock()
    rerank_lock = threading.Lock()

    def retrieve(text: str) -> list[Any]:
        with embed_lock:
            return retriever.retrieve_hybrid(text, dense_weight=0.3)

    def one(qid: str) -> dict[str, Any]:
        q = questions[qid]
        expected = {str(x) for x in q.get("expected_doc_ids", []) if x}
        lane_results = {name: retrieve(text) for name, text in views(str(q["question"])).items()}
        merged = rrf_merge([(lane_results[name], weight) for name, weight in (("original", 1.2), ("lexical", 1.0), ("semantic", 0.9), ("facet", 0.4))], 240)
        base = merged[:120]
        with rerank_lock:
            ranked = retriever.rerank(str(q["question"]), base, model_name="rerank", top_n=len(base), api_base=args.rerank_base, api_key_env="EMBEDDING_API_KEY", timeout=120)
        scores = [float(x.score) for x in ranked]
        if not scores:
            ranked = base
            scores = [0.0 for _ in ranked]
        s1 = scores[0]
        sorted_scores = sorted(scores)
        p75 = sorted_scores[max(0, int(0.75 * len(sorted_scores)) - 1)]
        # Relative margin is expressed in normalized rank-score units so it is
        # safe even if the remote reranker is not calibrated to [0, 1].
        lo, hi = min(scores), max(scores)
        denom = max(1e-9, hi - lo)
        normalized = [(s - lo) / denom for s in scores]
        variants: dict[str, list[Any]] = {
            "top6": ranked[:6],
            "top10": ranked[:10],
            "top16": ranked[:16],
            "top20": ranked[:20],
            "p75_max16": [x for x, s in zip(ranked, scores) if s >= p75][:16],
            "relative065_max16": [x for x, n in zip(ranked, normalized) if n >= 0.65][:16],
            "relative075_max16": [x for x, n in zip(ranked, normalized) if n >= 0.75][:16],
        }
        for name, vals in list(variants.items()):
            if len(vals) < 6:
                variants[name] = ranked[:6]
        def stats(vals: list[Any]) -> dict[str, Any]:
            r = recall(vals, expected)
            docs = {x.doc_id for x in vals if x.doc_id}
            return {**r, "chunk_count": len(vals), "doc_count": len(docs)}
        return {
            "question_id": qid,
            "question_type": q.get("question_type"),
            "expected_doc_ids": sorted(expected),
            "rerank_score_top1": s1,
            "rerank_score_p75": p75,
            "rerank_score_min": lo,
            "rerank_score_max": hi,
            "variants": {name: stats(vals) for name, vals in variants.items()},
        }

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(one, qid): qid for qid in qids}
        for i, future in enumerate(as_completed(futures), 1):
            rows.append(future.result())
            print(f"[{i}/{len(qids)}]", flush=True)
    rows.sort(key=lambda x: qids.index(x["question_id"]))
    variant_names = ["top6", "top10", "top16", "top20", "p75_max16", "relative065_max16", "relative075_max16"]
    groups = {"all": rows, "semantic": [r for r in rows if r["question_type"] == "semantic"], "controls": [r for r in rows if r["question_type"] != "semantic"]}
    report = {
        "schema_version": 1,
        "scope": "S3 threshold admission shadow over fixed AB50",
        "question_count": len(rows),
        "variants": variant_names,
        "groups": {group: {name: aggregate(values, name) for name in variant_names} for group, values in groups.items()},
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["groups"], ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
