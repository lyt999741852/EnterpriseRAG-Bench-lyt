"""Read-only top-1000 score-margin probe for the five raw-miss questions."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

STOP = {"what", "which", "where", "when", "does", "did", "have", "with", "from", "that", "this", "about", "into", "their", "there", "were", "been", "will", "would", "could", "should", "during", "between", "please", "according", "explain", "describe", "provide", "using"}


def call_json(base: str, path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(base.rstrip("/") + path, data=data, method="POST" if payload is not None else "GET", headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode())


def anchors(question: str) -> list[str]:
    out: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_.:/-]{2,}", question):
        low = token.lower().strip("._:/-")
        if low in STOP or token in out:
            continue
        if any(ch.isdigit() for ch in token) or token.isupper() or len(token) >= 6:
            out.append(token)
    return out[:20]


def hit_doc(source: dict) -> str:
    return str(source.get("doc_id") or source.get("chunk_id", "").split("__", 1)[0])


def rank(hits: list[dict], expected: set[str]) -> int | None:
    for n, hit in enumerate(hits, 1):
        if hit_doc(hit.get("_source") or {}) in expected:
            return n
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--es-url", default=os.environ.get("ES_URL", "http://127.0.0.1:9200"))
    ap.add_argument("--index", default=os.environ.get("ES_INDEX", "enterprise-rag-bge-small-v1"))
    ap.add_argument("--local-model", required=True)
    ap.add_argument("--top-k", type=int, default=1000)
    args = ap.parse_args()

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(args.local_model, local_files_only=True)
    questions = {}
    for line in Path(args.questions).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("question_id"):
            questions[row["question_id"]] = row
    qids = ["qst_0116", "qst_0184", "qst_0231", "qst_0251", "qst_0298"]
    mapping = call_json(f"{args.es_url}/{args.index}", "/_mapping")
    props = mapping[args.index]["mappings"]["properties"]
    dims = props.get("embedding", {}).get("dims")
    rows = []
    for qid in qids:
        q = questions[qid]
        expected = {str(x) for x in q.get("expected_doc_ids", []) if x}
        text = str(q.get("question", ""))
        vector = model.encode(text, normalize_embeddings=True).tolist()
        target = call_json(f"{args.es_url}/{args.index}", "/_search", {"size": 200, "_source": ["doc_id", "chunk_id", "embedding", "embedding_model"], "query": {"terms": {"doc_id": sorted(expected)}}, "sort": ["chunk_index"]}).get("hits", {}).get("hits", [])
        dense = call_json(f"{args.es_url}/{args.index}", "/_search", {"size": args.top_k, "knn": {"field": "embedding", "query_vector": vector, "k": args.top_k, "num_candidates": min(10000, args.top_k * 2)}, "_source": ["doc_id", "chunk_id"]}).get("hits", {}).get("hits", [])
        lexical = call_json(f"{args.es_url}/{args.index}", "/_search", {"size": args.top_k, "_source": ["doc_id", "chunk_id"], "query": {"multi_match": {"query": text, "fields": ["title^2", "text"]}}}).get("hits", {}).get("hits", [])
        anchor_text = " ".join(anchors(text)) or text
        anchor = call_json(f"{args.es_url}/{args.index}", "/_search", {"size": args.top_k, "_source": ["doc_id", "chunk_id"], "query": {"simple_query_string": {"query": anchor_text, "fields": ["title^2", "text"]}}}).get("hits", {}).get("hits", [])
        target_scores = []
        for hit in target:
            emb = (hit.get("_source") or {}).get("embedding") or []
            if len(emb) == len(vector):
                target_scores.append(sum(a * b for a, b in zip(vector, emb)))
        dense_scores = [float(h["_score"]) for h in dense if h.get("_score") is not None]
        target_max = max(target_scores, default=None)
        top_min = min(dense_scores, default=None)
        rows.append({"question_id": qid, "expected_document_ids": sorted(expected), "index_target_chunks": len(target), "target_embedding_models": sorted({(h.get("_source") or {}).get("embedding_model") for h in target if (h.get("_source") or {}).get("embedding_model")}), "index_embedding_dims": dims, "probe_dims": len(vector), "dense_top_k": args.top_k, "dense_target_rank": rank(dense, expected), "dense_target_max_score": target_max, "dense_tail_score": top_min, "dense_margin_to_tail": (top_min - target_max) if top_min is not None and target_max is not None else None, "bm25_question_target_rank": rank(lexical, expected), "bm25_anchor_target_rank": rank(anchor, expected), "anchor_tokens": anchors(text)})
    summary = {"dense_target_rank_le_1000": sum(r["dense_target_rank"] is not None for r in rows), "bm25_question_rank_le_1000": sum(r["bm25_question_target_rank"] is not None for r in rows), "bm25_anchor_rank_le_1000": sum(r["bm25_anchor_target_rank"] is not None for r in rows)}
    output = {"schema_version": 1, "scope": "R11.D raw-miss score-margin probe", "index": args.index, "rows": rows, "summary": summary}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
