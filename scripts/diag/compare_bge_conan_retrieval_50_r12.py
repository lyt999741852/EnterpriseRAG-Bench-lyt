"""Read-only direct-query retrieval comparison for the fixed 50-question set.

This intentionally bypasses rewrite, router, PageIndex, reranker and generation.
Gold document IDs are loaded only after retrieval to measure Recall@K.
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


def call_json(url: str, payload: dict | None = None, headers: dict[str, str] | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(url, data=data, method="POST" if payload is not None else "GET", headers=headers or {"Content-Type": "application/json"})
    with urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode())


def embed(base: str, model: str, text: str, key: str) -> list[float]:
    body = {"model": model, "input": [text], "encoding_format": "float"}
    result = call_json(base.rstrip("/") + "/embeddings", body, {"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    return result["data"][0]["embedding"]


def doc_id(hit: dict) -> str:
    source = hit.get("_source") or {}
    return str(source.get("doc_id") or source.get("chunk_id", hit.get("_id", "")).split("__", 1)[0])


def retrieve(base: str, index: str, vector: list[float], k: int) -> list[dict]:
    body = {"size": k, "knn": {"field": "embedding", "query_vector": vector, "k": k, "num_candidates": min(10000, max(2 * k, 100))}, "_source": ["doc_id", "chunk_id"]}
    try:
        return call_json(f"{base.rstrip('/')}/{index}/_search", body).get("hits", {}).get("hits", [])
    except Exception:
        # ES7 fallback used by the Conan service.
        body = {"size": k, "_source": ["doc_id", "chunk_id"], "query": {"script_score": {"query": {"match_all": {}}, "script": {"source": "cosineSimilarity(params.q, 'embedding') + 1.0", "params": {"q": vector}}}}}
        return call_json(f"{base.rstrip('/')}/{index}/_search", body).get("hits", {}).get("hits", [])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default="questions.jsonl")
    ap.add_argument("--output", required=True)
    ap.add_argument("--bge-es", default="http://127.0.0.1:9200")
    ap.add_argument("--bge-index", default="enterprise-rag-bge-small-v1")
    ap.add_argument("--conan-es", default="http://10.72.100.29:31920")
    ap.add_argument("--conan-index", default="enterprise-rag-qwen3-emb-v3-conan448")
    ap.add_argument("--conan-embedding", default="http://10.72.55.209:7993/v1")
    ap.add_argument("--embedding-key", default=os.environ.get("EMBEDDING_API_KEY", "123456"))
    ap.add_argument("--bge-model", default="BAAI/bge-small-en-v1.5")
    ap.add_argument("--max-k", type=int, default=1000)
    args = ap.parse_args()

    from sentence_transformers import SentenceTransformer

    bge_model = SentenceTransformer(args.bge_model, local_files_only=True)
    questions = {r["question_id"]: r for r in (json.loads(x) for x in Path(args.questions).read_text(encoding="utf-8").splitlines()) if r.get("question_id")}
    rows = []
    for n, qid in enumerate(QIDS, 1):
        text = questions[qid]["question"]
        expected = {str(x) for x in questions[qid].get("expected_doc_ids", []) if x}
        bge_vector = bge_model.encode(text, normalize_embeddings=True).tolist()
        conan_vector = embed(args.conan_embedding, "embedding", text, args.embedding_key)
        if len(bge_vector) != 384 or len(conan_vector) != 1792:
            raise RuntimeError(f"unexpected dimensions for {qid}: BGE={len(bge_vector)} Conan={len(conan_vector)}")
        bge_hits = retrieve(args.bge_es, args.bge_index, bge_vector, args.max_k)
        conan_hits = retrieve(args.conan_es, args.conan_index, conan_vector, args.max_k)
        bge_docs = [doc_id(h) for h in bge_hits]
        conan_docs = [doc_id(h) for h in conan_hits]
        def rank(docs: list[str]) -> int | None:
            for i, d in enumerate(docs, 1):
                if d in expected:
                    return i
            return None
        rows.append({"question_id": qid, "question_type": questions[qid].get("question_type"), "expected_doc_ids": sorted(expected), "bge_rank": rank(bge_docs), "conan_rank": rank(conan_docs), "bge_hit_count": len(bge_hits), "conan_hit_count": len(conan_hits), "bge_top_docs": bge_docs[:30], "conan_top_docs": conan_docs[:30]})
        print(f"[{n}/{len(QIDS)}] {qid}: BGE={rows[-1]['bge_rank']} Conan={rows[-1]['conan_rank']}", flush=True)
    ks = [30, 120, 240, args.max_k]
    summary = {"question_count": len(rows), "dimensions": {"bge": 384, "conan": 1792}, "recall_at_k": {"bge": {str(k): sum(r["bge_rank"] is not None and r["bge_rank"] <= k for r in rows) / len(rows) * 100 for k in ks}, "conan": {str(k): sum(r["conan_rank"] is not None and r["conan_rank"] <= k for r in rows) / len(rows) * 100 for k in ks}}, "bge_raw_hit": sum(r["bge_rank"] is not None for r in rows), "conan_raw_hit": sum(r["conan_rank"] is not None for r in rows)}
    output = {"schema_version": 1, "scope": "R12 direct original-question dense retrieval comparison", "bge_index": args.bge_index, "conan_index": args.conan_index, "summary": summary, "rows": rows}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
