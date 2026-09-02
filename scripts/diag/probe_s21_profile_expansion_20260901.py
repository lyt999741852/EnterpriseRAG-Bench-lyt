"""S2.1: document-profile retrieval followed by source-chunk expansion."""
from __future__ import annotations
import argparse, json, statistics, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

def call_json(url: str, payload: dict) -> dict:
    req = Request(url, data=json.dumps(payload).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())

def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    return {str(r["question_id"]): r for r in (json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()) if r.get("question_id")}

def doc_id(hit: dict[str, Any]) -> str:
    src = hit.get("_source") or {}
    return str(src.get("doc_id") or src.get("profile_id") or src.get("chunk_id") or hit.get("_id", "")).split("__", 1)[0]

def rrf(lists: list[list[str]], weights: list[float], top_n: int = 100) -> list[str]:
    scores: dict[str, float] = {}
    for w, values in zip(weights, lists):
        for rank, value in enumerate(values, 1):
            scores[value] = scores.get(value, 0.0) + w / (60 + rank)
    return [v for v, _ in sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:top_n]]

def stats(values: list[str], expected: set[str], cuts: tuple[int, ...]) -> dict[str, Any]:
    out = {}
    for k in cuts:
        found = set(values[:k]) & expected
        out[str(k)] = {"hit": bool(found), "expected_found": len(found), "expected_total": len(expected), "coverage_pct": round(100 * len(found) / len(expected), 2) if expected else None}
    out["first_expected_rank"] = next((i for i, v in enumerate(values, 1) if v in expected), None)
    return out

def aggregate(rows: list[dict[str, Any]], field: str, cuts: tuple[int, ...]) -> dict[str, Any]:
    out = {"question_count": len(rows)}
    for k in cuts:
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
    ap.add_argument("--questions", type=Path, required=True); ap.add_argument("--o0-funnel", type=Path, required=True); ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--es", default="http://127.0.0.1:9200"); ap.add_argument("--profile-index", default="o392_bge_doc_profile_20260901"); ap.add_argument("--chunk-index", default="o391_bge_meta_bm25_20260901"); ap.add_argument("--model", default="BAAI/bge-small-en-v1.5"); ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()
    qs = load_jsonl(args.questions); funnel = json.loads(args.o0_funnel.read_text(encoding="utf-8"))
    effective = [str(r["question_id"]) for r in funnel.get("rows", []) if r.get("expected_document_ids") and str(r.get("question_id")) in qs]
    semantic = {qid for qid in effective if qs[qid].get("question_type") == "semantic"}
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(args.model, local_files_only=True)
    vectors = model.encode([str(qs[qid]["question"]) for qid in effective], normalize_embeddings=True, batch_size=32, show_progress_bar=False).tolist()
    vector_by_id = dict(zip(effective, vectors)); cuts = (10, 20, 30, 50)

    def one(qid: str) -> dict[str, Any]:
        q = str(qs[qid]["question"]); expected = {str(x) for x in qs[qid].get("expected_doc_ids", []) if x}; base = f"{args.es.rstrip('/')}/{args.profile_index}/_search"; started = time.perf_counter()
        dense_body = {"size": 100, "knn": {"field": "embedding", "query_vector": vector_by_id[qid], "k": 100, "num_candidates": 300}, "_source": ["doc_id", "profile_id", "chunk_id", "chunk_index", "title", "file_path"]}
        bm25_body = {"size": 100, "query": {"multi_match": {"query": q, "fields": ["profile_text", "lexical_context^1.2", "title^1.5", "file_path"], "type": "best_fields", "operator": "or"}}, "_source": ["doc_id", "profile_id", "chunk_id", "chunk_index", "title", "file_path"]}
        dh = call_json(base, dense_body).get("hits", {}).get("hits", []); bh = call_json(base, bm25_body).get("hits", {}).get("hits", [])
        dense = list(dict.fromkeys(doc_id(h) for h in dh)); bm25 = list(dict.fromkeys(doc_id(h) for h in bh)); fused = rrf([dense, bm25], [1.0, 1.2], 100)
        expanded: list[str] = []; expansion_count = 0
        selected = fused[:50]
        if selected:
            chunk_body = {"size": min(500, len(selected) * 20), "query": {"terms": {"doc_id": selected}}, "sort": [{"chunk_index": {"order": "asc"}}], "_source": ["doc_id", "chunk_id", "chunk_index"]}
            ch = call_json(f"{args.es.rstrip('/')}/{args.chunk_index}/_search", chunk_body).get("hits", {}).get("hits", [])
            # Expansion must preserve the profile rank.  Elasticsearch returns
            # chunks sorted by chunk_index, which is useful for context order
            # but would make top-10/20/30 stats depend on chunk position rather
            # than document retrieval rank.
            returned_docs = {doc_id(h) for h in ch}
            expanded = [d for d in selected if d in returned_docs]
            expansion_count = len(ch)
        return {"question_id": qid, "question_type": qs[qid].get("question_type"), "expected_document_ids": sorted(expected), "profile_dense": stats(dense, expected, cuts), "profile_bm25": stats(bm25, expected, cuts), "profile_fused": stats(fused, expected, cuts), "expanded_chunks": stats(expanded, expected, cuts), "profile_dense_top": dense[:10], "profile_bm25_top": bm25[:10], "profile_fused_top": fused[:10], "expanded_chunk_count": expansion_count, "gold_profile_hit": bool(set(dense + bm25) & expected), "gold_expanded": bool(set(expanded) & expected), "latency_ms": round((time.perf_counter() - started) * 1000, 2)}

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(one, qid): qid for qid in effective}
        for i, future in enumerate(as_completed(futures), 1):
            rows.append(future.result())
            if i % 25 == 0 or i == len(effective): print(f"[{i}/{len(effective)}]", flush=True)
    rows.sort(key=lambda r: effective.index(r["question_id"]))
    groups = {"semantic": [r for r in rows if r["question_id"] in semantic], "controls": [r for r in rows if r["question_id"] not in semantic], "effective": rows}
    report = {"schema_version": 1, "scope": "S2.1 document-profile dense/BM25 retrieval followed by source chunk expansion", "profile_index": args.profile_index, "chunk_index": args.chunk_index, "effective_question_count": len(rows), "semantic_question_count": len(semantic), "cutoffs": list(cuts), "groups": {name: {"question_count": len(group), "profile_dense": aggregate(group, "profile_dense", cuts), "profile_bm25": aggregate(group, "profile_bm25", cuts), "profile_fused": aggregate(group, "profile_fused", cuts), "expanded_chunks": aggregate(group, "expanded_chunks", cuts), "gold_profile_hit_count": sum(r["gold_profile_hit"] for r in group), "gold_expanded_count": sum(r["gold_expanded"] for r in group), "mean_latency_ms": round(statistics.mean(r["latency_ms"] for r in group), 2) if group else None} for name, group in groups.items()}, "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); print(json.dumps(report["groups"], ensure_ascii=False)); return 0

if __name__ == "__main__":
    raise SystemExit(main())
