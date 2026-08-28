"""Read-only pilot for alternate 1792-dim embedding separation.

The current BGE dense/BM25 candidate pool is kept fixed.  Conan vectors are
computed only for the question, that pool, and the expected target chunks;
no Elasticsearch vector field is written or queried with incompatible dims.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def es_search(base: str, index: str, body: dict) -> list[dict]:
    req = Request(base.rstrip("/") + f"/{index}/_search", data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode()).get("hits", {}).get("hits", [])


def embed(url: str, key: str, texts: list[str]) -> list[list[float]]:
    req = Request(url, data=json.dumps({"model": "embedding", "input": texts, "encoding_format": "float"}).encode(), method="POST", headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urlopen(req, timeout=180) as response:
            payload = json.loads(response.read().decode())
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"embedding HTTP {exc.code}: {detail[:500]}") from exc
    return [row["embedding"] for row in sorted(payload["data"], key=lambda row: row.get("index", 0))]


def chunks(values: list[str], size: int):
    for i in range(0, len(values), size):
        yield values[i:i + size]


def identity(hit: dict) -> str:
    source = hit.get("_source") or {}
    return str(source.get("chunk_id") or hit.get("_id", ""))


def doc_id(hit: dict) -> str:
    source = hit.get("_source") or {}
    return str(source.get("doc_id") or identity(hit).split("__", 1)[0])


def cosine(left: list[float], right: list[float]) -> float:
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--local-model", required=True)
    ap.add_argument("--es-url", default=os.environ.get("ES_URL", "http://127.0.0.1:9200"))
    ap.add_argument("--index", default=os.environ.get("ES_INDEX", "enterprise-rag-bge-small-v1"))
    ap.add_argument("--embedding-url", default="http://10.72.55.209:7993/v1/embeddings")
    ap.add_argument("--embedding-key", default=os.environ.get("EMBEDDING_API_KEY", "123456"))
    ap.add_argument("--candidate-k", type=int, default=300)
    args = ap.parse_args()

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(args.local_model, local_files_only=True)
    questions = {}
    for line in Path(args.questions).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("question_id"):
            questions[row["question_id"]] = row
    qids = ["qst_0116", "qst_0184", "qst_0231", "qst_0251", "qst_0298"]
    rows = []
    for qid in qids:
        question = str(questions[qid]["question"])
        expected = {str(x) for x in questions[qid].get("expected_doc_ids", []) if x}
        qv = model.encode(question, normalize_embeddings=True).tolist()
        dense_hits = es_search(args.es_url, args.index, {"size": args.candidate_k, "knn": {"field": "embedding", "query_vector": qv, "k": args.candidate_k, "num_candidates": min(2000, args.candidate_k * 2)}, "_source": ["doc_id", "chunk_id", "title", "text"]})
        bm25_hits = es_search(args.es_url, args.index, {"size": args.candidate_k, "query": {"multi_match": {"query": question, "fields": ["title^2", "text"]}}, "_source": ["doc_id", "chunk_id", "title", "text"]})
        target_hits = es_search(args.es_url, args.index, {"size": 200, "query": {"terms": {"doc_id": sorted(expected)}}, "_source": ["doc_id", "chunk_id", "title", "text"]})
        by_id = {}
        origin = {}
        for label, hits in (("bge_dense", dense_hits), ("bm25", bm25_hits), ("target", target_hits)):
            for hit in hits:
                cid = identity(hit)
                if cid not in by_id:
                    by_id[cid] = hit
                    origin[cid] = [label]
                elif label not in origin[cid]:
                    origin[cid].append(label)
        ids = list(by_id)
        # Conan accepts at most 512 tokens per item; cap characters
        # conservatively for this pilot rather than changing indexed chunks.
        texts = [(str((by_id[cid].get("_source") or {}).get("title", "")) + "\n" + str((by_id[cid].get("_source") or {}).get("text", "")))[:1000] for cid in ids]
        vectors = []
        for batch in chunks([question] + texts, 16):
            vectors.extend(embed(args.embedding_url, args.embedding_key, batch))
        alt_q = vectors[0]
        scored = []
        for cid, vector in zip(ids, vectors[1:]):
            score = cosine(alt_q, vector)
            scored.append((score, cid))
        scored.sort(reverse=True)
        target_ids = {cid for cid, hit in by_id.items() if doc_id(hit) in expected}
        target_ranks = [n for n, (_, cid) in enumerate(scored, 1) if cid in target_ids]
        target_scores = [score for score, cid in scored if cid in target_ids]
        rows.append({"question_id": qid, "candidate_pool_size": len(ids), "bge_dense_candidates": len(dense_hits), "bm25_candidates": len(bm25_hits), "target_chunks": len(target_ids), "target_pool_origins": sorted({label for cid in target_ids for label in origin.get(cid, [])}), "conan_dim": len(alt_q), "alternate_target_ranks": target_ranks, "alternate_target_scores": target_scores, "alternate_candidate_tail_score": scored[-1][0] if scored else None, "alternate_top10": [{"chunk_id": cid, "score": score, "origin": origin.get(cid, [])} for score, cid in scored[:10]]})
    summary = {"questions_with_target_rank_le_pool": sum(bool(row["alternate_target_ranks"]) for row in rows), "questions_with_target_rank_le_30": sum(any(rank <= 30 for rank in row["alternate_target_ranks"]) for row in rows), "conan_dimension": sorted({row["conan_dim"] for row in rows})}
    output = {"schema_version": 1, "scope": "R11.F alternate embedding separation pilot", "index": args.index, "candidate_k": args.candidate_k, "summary": summary, "rows": rows}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
