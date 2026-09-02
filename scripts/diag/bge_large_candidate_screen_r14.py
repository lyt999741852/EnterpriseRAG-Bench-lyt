"""Conditional 50-question screen for BGE-large on a shared candidate pool.

Candidates are BGE-small top-200 chunks for each fixed question plus all chunks
from its gold documents. This is intentionally not full-corpus recall; it
isolates whether BGE-large can reorder a practical candidate pool better than
BGE-small before paying for a full 928k-chunk rebuild.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

QIDS = [
    "qst_0013", "qst_0018", "qst_0022", "qst_0030", "qst_0035", "qst_0041",
    "qst_0050", "qst_0056", "qst_0079", "qst_0082", "qst_0093", "qst_0107",
    "qst_0112", "qst_0116", "qst_0119", "qst_0125", "qst_0154", "qst_0169",
    "qst_0184", "qst_0197", "qst_0211", "qst_0231", "qst_0236", "qst_0241",
    "qst_0251", "qst_0271", "qst_0272", "qst_0280", "qst_0291", "qst_0298",
    "qst_0301", "qst_0322", "qst_0324", "qst_0328", "qst_0341", "qst_0350",
    "qst_0356", "qst_0362", "qst_0386", "qst_0390", "qst_0406", "qst_0413",
    "qst_0416", "qst_0432", "qst_0447", "qst_0459", "qst_0470", "qst_0480",
    "qst_0491", "qst_0498",
]


def call_json(url: str, payload: dict | None = None, method: str | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(url, data=data, method=method or ("POST" if payload is not None else "GET"), headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=300) as response:
        return json.loads(response.read().decode())


def source(hit: dict) -> dict:
    return hit.get("_source") or {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default="questions.jsonl")
    ap.add_argument("--es", default="http://127.0.0.1:9200")
    ap.add_argument("--small-index", default="enterprise-rag-bge-small-v1")
    ap.add_argument("--candidate-k", type=int, default=200)
    ap.add_argument("--large-model", default="/data06/embedding-models/bge-large-en-v1.5")
    ap.add_argument("--small-model", default="/opt/enterprise-rag-bench/model_cache/hub/models--BAAI--bge-small-en-v1.5/snapshots/5c38ec7c405ec4b44b94cc5a9bb96e735b38267a")
    ap.add_argument("--large-index", default="enterprise-rag-bge-large-r14-candidates50")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    from sentence_transformers import SentenceTransformer
    import numpy as np

    questions = {
        r["question_id"]: r
        for r in (json.loads(line) for line in Path(args.questions).read_text(encoding="utf-8").splitlines())
        if r.get("question_id")
    }
    small = SentenceTransformer(args.small_model, device="cpu", local_files_only=True)
    candidates: dict[str, dict] = {}
    for n, qid in enumerate(QIDS, 1):
        q = questions[qid]
        qvec = small.encode(q["question"], normalize_embeddings=True).tolist()
        body = {"size": args.candidate_k, "knn": {"field": "embedding", "query_vector": qvec, "k": args.candidate_k, "num_candidates": min(10000, max(2 * args.candidate_k, 100))}, "_source": ["doc_id", "chunk_id", "source_type", "text", "chunk_index", "title"]}
        try:
            hits = call_json(f"{args.es.rstrip('/')}/{args.small_index}/_search", body).get("hits", {}).get("hits", [])
        except Exception:
            body = {"size": args.candidate_k, "_source": ["doc_id", "chunk_id", "source_type", "text", "chunk_index", "title"], "query": {"script_score": {"query": {"match_all": {}}, "script": {"source": "cosineSimilarity(params.q, 'embedding') + 1.0", "params": {"q": qvec}}}}}
            hits = call_json(f"{args.es.rstrip('/')}/{args.small_index}/_search", body).get("hits", {}).get("hits", [])
        for hit in hits:
            s = source(hit)
            if s.get("chunk_id"):
                candidates.setdefault(str(s["chunk_id"]), s)
        for doc_id in q.get("expected_doc_ids", []):
            body = {"size": 2000, "_source": ["doc_id", "chunk_id", "source_type", "text", "chunk_index", "title"], "query": {"term": {"doc_id": str(doc_id)}}}
            for hit in call_json(f"{args.es.rstrip('/')}/{args.small_index}/_search", body).get("hits", {}).get("hits", []):
                s = source(hit)
                if s.get("chunk_id"):
                    candidates.setdefault(str(s["chunk_id"]), s)
        print(f"COLLECT [{n}/{len(QIDS)}] {qid} candidates={len(candidates)}", flush=True)

    records = list(candidates.values())
    texts = [str(r.get("text") or "") for r in records]
    print(f"ENCODE candidates={len(records)}", flush=True)
    small_model = SentenceTransformer(args.small_model, device="cpu", local_files_only=True)
    large_model = SentenceTransformer(args.large_model, device="cpu", local_files_only=True)
    small_doc = np.asarray(small_model.encode(texts, batch_size=128, normalize_embeddings=True, show_progress_bar=True), dtype=np.float32)
    large_doc = np.asarray(large_model.encode(texts, batch_size=128, normalize_embeddings=True, show_progress_bar=True), dtype=np.float32)

    # Create an independent 1024-dim ES index for later direct inspection.
    idx_url = f"{args.es.rstrip('/')}/{args.large_index}"
    try:
        call_json(idx_url, {"mappings": {"dynamic": "strict", "properties": {
            "chunk_id": {"type": "keyword"}, "doc_id": {"type": "keyword"}, "source_type": {"type": "keyword"},
            "text": {"type": "text"}, "chunk_index": {"type": "integer"}, "title": {"type": "text"},
            "embedding": {"type": "dense_vector", "dims": 1024, "index": True, "similarity": "cosine"},
        }}}, method="PUT")
    except Exception:
        pass
    for start in range(0, len(records), 64):
        lines = []
        for i in range(start, min(start + 64, len(records))):
            r = records[i]
            lines.append(json.dumps({"index": {"_index": args.large_index, "_id": r["chunk_id"]}}, separators=(",", ":")))
            doc = {k: r.get(k) for k in ("chunk_id", "doc_id", "source_type", "text", "chunk_index", "title")}
            doc["embedding"] = large_doc[i].tolist()
            lines.append(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
        req = Request(f"{args.es.rstrip('/')}/_bulk", data=("\n".join(lines) + "\n").encode(), method="POST", headers={"Content-Type": "application/x-ndjson"})
        with urlopen(req, timeout=300) as response:
            result = json.loads(response.read().decode())
        if result.get("errors"):
            raise RuntimeError(f"bulk indexing failed at {start}")
        print(f"INDEX {min(start + 64, len(records))}/{len(records)}", flush=True)
    call_json(f"{idx_url}/_refresh", {})

    by_id = {str(r["chunk_id"]): i for i, r in enumerate(records)}
    rows = []
    for qid in QIDS:
        q = questions[qid]
        q_small = np.asarray(small_model.encode(q["question"], normalize_embeddings=True), dtype=np.float32)
        q_large = np.asarray(large_model.encode(q["question"], normalize_embeddings=True), dtype=np.float32)
        scores = {"bge_small": small_doc @ q_small, "bge_large": large_doc @ q_large}
        expected = {str(x) for x in q.get("expected_doc_ids", []) if x}
        result = {"question_id": qid, "question_type": q.get("question_type"), "expected_doc_ids": sorted(expected)}
        for name, vals in scores.items():
            order = np.argsort(-vals)
            rank = next((i + 1 for i in order if str(records[int(i)].get("doc_id")) in expected), None)
            result[f"{name}_rank"] = int(rank) if rank is not None else None
        rows.append(result)

    ks = [30, 120, 240, 1000]
    summary = {name: {str(k): round(sum(r[f"{name}_rank"] is not None and r[f"{name}_rank"] <= k for r in rows) / len(rows) * 100, 2) for k in ks} for name in ("bge_small", "bge_large")}
    output = {"schema_version": 1, "scope": "R14 conditional candidate-pool screen; not full-corpus recall", "candidate_k_per_question": args.candidate_k, "candidate_count": len(records), "large_index": args.large_index, "summary": summary, "rows": rows}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
