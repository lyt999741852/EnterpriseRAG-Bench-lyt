"""S4.5 document-aware admission and edge-packed context generation.

Uses only retrieval outputs for online admission: final reranked candidates
plus an append-only, document-diverse reserve from the pre-rerank union. Gold
document IDs are read only after generation for per-question diagnostics.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import sys
ROOT = str(Path(__file__).resolve().parents[2])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.elasticsearch_backend import ElasticsearchBackend, ElasticsearchConfig
from src.generator import Generator, GeneratorConfig
from src.llm import LLMConfig
from src.retriever import RetrieveResult


def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row["question_id"]): row for row in (
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    )}


def make_generator(base_url: str) -> Generator:
    return Generator(GeneratorConfig(
        llm=LLMConfig(
            provider="openai_compatible", api_base=base_url,
            api_key_env="DPV4_API_KEY", model_name="deepseek-v4-flash",
            temperature=0.0, max_tokens=8192, timeout=180,
            retry_attempts=3, retry_backoff_seconds=1.0,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        ),
        max_context_chunks=10,
        max_chunks_per_doc=2,
        max_document_ids=10,
        evidence_selection_enabled=True,
        evidence_selection_candidate_chunks=30,
        evidence_selection_max_chunks=10,
        evidence_selection_mode="precision_v3",
        evidence_selection_anchor_chunks=2,
        evidence_selection_fallback_chunks=4,
        evidence_selection_fail_closed=False,
        fact_verification_enabled=True,
        final_answer_audit_enabled=True,
    ))


def edge_pack(items: list[RetrieveResult]) -> list[RetrieveResult]:
    """Place high-ranked items at both context edges, with reserve in middle."""
    if len(items) <= 2:
        return list(items)
    out: list[RetrieveResult | None] = [None] * len(items)
    left, right = 0, len(items) - 1
    for i, item in enumerate(items):
        if i % 2 == 0:
            out[left] = item; left += 1
        else:
            out[right] = item; right -= 1
    return [x for x in out if x is not None]


def build_candidates(
    final_items: list[RetrieveResult], pre_items: list[RetrieveResult],
    max_chunks: int = 30, max_docs: int = 10, per_doc: int = 2,
) -> tuple[list[RetrieveResult], int]:
    """Keep reranked evidence, then append one chunk per unseen pre-rerank doc."""
    selected: list[RetrieveResult] = []
    seen_chunks: set[str] = set()
    per_doc_count: dict[str, int] = {}
    for item in final_items:
        if item.chunk_id in seen_chunks:
            continue
        if len(set(per_doc_count)) >= max_docs and item.doc_id not in per_doc_count:
            continue
        if per_doc_count.get(item.doc_id, 0) >= per_doc:
            continue
        selected.append(item); seen_chunks.add(item.chunk_id)
        per_doc_count[item.doc_id] = per_doc_count.get(item.doc_id, 0) + 1
        if len(selected) >= max_chunks:
            return edge_pack(selected), 0
    before = len(selected)
    for item in pre_items:
        if len(selected) >= max_chunks:
            break
        if item.chunk_id in seen_chunks:
            continue
        if len(set(per_doc_count)) >= max_docs and item.doc_id not in per_doc_count:
            continue
        if per_doc_count.get(item.doc_id, 0) >= per_doc:
            continue
        selected.append(item); seen_chunks.add(item.chunk_id)
        per_doc_count[item.doc_id] = per_doc_count.get(item.doc_id, 0) + 1
    return edge_pack(selected), len(selected) - before


def doc_coverage(doc_ids: list[str], expected: set[str]) -> dict[str, Any]:
    found = [x for x in dict.fromkeys(doc_ids) if x in expected]
    return {
        "hit": bool(found), "expected_found": len(found),
        "expected_total": len(expected),
        "coverage_pct": round(100 * len(found) / len(expected), 2) if expected else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", type=Path, required=True)
    ap.add_argument("--retrieval-report", type=Path, required=True)
    ap.add_argument("--answers", type=Path, required=True)
    ap.add_argument("--generation-report", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--es", default="http://127.0.0.1:9200")
    ap.add_argument("--index", default="enterprise-rag-bge-small-v1")
    ap.add_argument("--dpv4-base", default="http://10.72.100.29:18380/v1")
    args = ap.parse_args()
    questions = load_jsonl(args.questions)
    report = json.loads(args.retrieval_report.read_text(encoding="utf-8"))
    rows = list(report.get("rows") or [])
    backend = ElasticsearchBackend(ElasticsearchConfig(
        url=args.es, index_name=args.index, alias_name="enterprise-rag-bge-small", request_timeout=180,
    ))
    all_ids: list[str] = []
    for row in rows:
        all_ids.extend(str(x) for x in row.get("augmented_pre_rerank_chunk_ids", [])[:500] if x)
        all_ids.extend(str(x) for x in row.get("augmented_candidate_chunk_ids", [])[:30] if x)
    all_ids = list(dict.fromkeys(all_ids))
    chunks: dict[str, RetrieveResult] = {}
    missing: list[str] = []
    # Full500 reports can reference hundreds of thousands of chunk IDs.  Keep
    # _mget requests bounded so the ES HTTP body and response remain stable.
    for start in range(0, len(all_ids), 5000):
        response = backend._request("POST", f"/{args.index}/_mget", {"ids": all_ids[start:start + 5000]})
        for doc in response.get("docs", []):
            if not doc.get("found"):
                missing.append(str(doc.get("_id", ""))); continue
            src = doc.get("_source", {})
            cid = str(src.get("chunk_id", doc.get("_id", "")))
            chunks[cid] = RetrieveResult(
                chunk_id=cid, doc_id=str(src.get("doc_id", "")),
                source_type=str(src.get("source_type", "")), text=str(src.get("text", "")), score=0.0,
            )

    def one(row: dict[str, Any]) -> dict[str, Any]:
        qid = str(row["question_id"]); q = questions[qid]; question = str(q["question"])
        expected = {str(x) for x in row.get("expected_document_ids", []) if x}
        final = [chunks[x] for x in row.get("augmented_candidate_chunk_ids", [])[:30] if x in chunks]
        pre = [chunks[x] for x in row.get("augmented_pre_rerank_chunk_ids", [])[:500] if x in chunks]
        candidates, reserve_count = build_candidates(final, pre)
        candidate_docs = list(dict.fromkeys(x.doc_id for x in candidates if x.doc_id))
        pre_docs = list(dict.fromkeys(x.doc_id for x in pre if x.doc_id))
        final_docs = list(dict.fromkeys(x.doc_id for x in final if x.doc_id))
        started = time.perf_counter()
        answer, generated_docs = make_generator(args.dpv4_base).generate_with_sources(
            question, candidates, q.get("question_type")
        )
        return {
            "question_id": qid, "question_type": q.get("question_type"),
            "answer": answer, "document_ids": generated_docs,
            "pre_rerank_coverage": doc_coverage(pre_docs, expected),
            "reranked_coverage": doc_coverage(final_docs, expected),
            "admitted_candidate_coverage": doc_coverage(candidate_docs, expected),
            "generated_coverage": doc_coverage(generated_docs, expected),
            "pre_rerank_doc_count": len(pre_docs), "reranked_doc_count": len(final_docs),
            "admitted_doc_count": len(candidate_docs), "reserve_chunk_count": reserve_count,
            "candidate_chunk_count": len(candidates),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(one, row): str(row["question_id"]) for row in rows}
        for i, future in enumerate(as_completed(futures), 1):
            results.append(future.result()); print(f"[{i}/{len(rows)}]", flush=True)
    order = {str(row["question_id"]): i for i, row in enumerate(rows)}
    results.sort(key=lambda x: order[x["question_id"]])
    args.answers.parent.mkdir(parents=True, exist_ok=True)
    args.answers.write_text("\n".join(json.dumps({k: r[k] for k in ("question_id", "answer", "document_ids")}, ensure_ascii=False) for r in results) + "\n", encoding="utf-8")
    payload = {
        "schema_version": 1, "scope": "S4.5 document-aware reserve + edge-packed context",
        "question_count": len(results), "retrieval_report": str(args.retrieval_report),
        "llm": "deepseek-v4-flash", "correction": "no-correction (scoring stage)",
        "missing_retrieval_chunks": missing,
        "mean_reserve_chunk_count": round(statistics.mean(r["reserve_chunk_count"] for r in results), 2),
        "mean_admitted_doc_count": round(statistics.mean(r["admitted_doc_count"] for r in results), 2),
        "mean_generation_latency_ms": round(statistics.mean(r["latency_ms"] for r in results), 2),
        "rows": results,
    }
    args.generation_report.parent.mkdir(parents=True, exist_ok=True)
    args.generation_report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("question_count", "missing_retrieval_chunks", "mean_reserve_chunk_count", "mean_admitted_doc_count", "mean_generation_latency_ms")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
