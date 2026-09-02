"""Compare 160+16, 128+16 and 448+32 on a deterministic 1000-doc sample."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


ROOT = "/opt/enterprise-rag-bench/app"
ES = "http://10.72.100.29:31920"
EMBED = "http://10.72.55.209:7993/v1/embeddings"
KEY = "123456"
DIM = 1792
OVER = (160, 16)
VARIANTS = ((160, 16), (128, 16), (448, 32))


def request(method: str, path: str, payload=None, content_type="application/json"):
    data = None
    if payload is not None:
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    req = urllib.request.Request(f"{ES}{path}", data=data, method=method, headers={
        "Content-Type": content_type,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        if method == "DELETE" and exc.code == 404:
            return {}
        raise
    return json.loads(raw.decode()) if raw else {}


def fixed_chunks(text: str, size: int, overlap: int):
    tokens = list(re.finditer(r"\S+", text))
    if len(tokens) <= size:
        return [(text, 0, len(text), 0)]
    out = []
    step = size - overlap
    for index, start_i in enumerate(range(0, len(tokens), step)):
        end_i = min(start_i + size, len(tokens))
        start, end = tokens[start_i].start(), tokens[end_i - 1].end()
        out.append((text[start:end], start, end, index))
    return out


def embed_one(text: str, stats: dict):
    body = json.dumps({"model": "embedding", "input": [text], "encoding_format": "float"}).encode()
    req = urllib.request.Request(EMBED, data=body, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {KEY}",
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            payload = json.loads(response.read().decode())
        return [(text, payload["data"][0]["embedding"])]
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code != 400:
            raise
        stats["http400"] += 1
        if len(text) < 80:
            raise RuntimeError(f"unsplittable text after HTTP 400: {len(text)} chars")
        midpoint = len(text) // 2
        cut = text.rfind(" ", 0, midpoint)
        if cut < 40:
            cut = text.find(" ", midpoint)
        if cut <= 0 or cut >= len(text) - 1:
            cut = midpoint
        left, right = text[:cut].strip(), text[cut:].strip()
        return embed_one(left, stats) + embed_one(right, stats)


def build_variant(docs, size: int, overlap: int):
    chunks = []
    for doc_id, source_type, text in docs:
        for chunk_text, start, end, index in fixed_chunks(text, size, overlap):
            chunks.append({
                "chunk_id": f"{doc_id}__exp-{size}-{overlap}__chunk{index:05d}",
                "doc_id": doc_id, "source_type": source_type, "text": chunk_text,
                "chunk_index": index, "char_start": start, "char_end": end,
            })
    stats = {"http400": 0}
    lock = threading.Lock()

    def work(chunk):
        local = {"http400": 0}
        pieces = embed_one(chunk["text"], local)
        with lock:
            stats["http400"] += local["http400"]
        return chunk, pieces

    started = time.perf_counter()
    encoded = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for chunk, pieces in pool.map(work, chunks):
            for piece_index, (part, vector) in enumerate(pieces):
                item = dict(chunk)
                item["text"] = part
                if len(pieces) > 1:
                    item["chunk_id"] = f"{chunk['chunk_id']}__p{piece_index}"
                item["embedding"] = vector
                encoded.append(item)
    elapsed = time.perf_counter() - started
    index = f"enterprise-rag-exp-{size}-{overlap}-20260807"
    request("DELETE", f"/{index}")
    request("PUT", f"/{index}", {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0, "refresh_interval": "-1"},
        "mappings": {"dynamic": "strict", "properties": {
            "chunk_id": {"type": "keyword"}, "doc_id": {"type": "keyword"},
            "source_type": {"type": "keyword"}, "text": {"type": "text"},
            "chunk_index": {"type": "integer"}, "char_start": {"type": "integer"},
            "char_end": {"type": "integer"},
            "embedding": {"type": "dense_vector", "dims": DIM, "index": True, "similarity": "cosine"},
        }},
    })
    for start in range(0, len(encoded), 64):
        batch = encoded[start:start + 64]
        lines = []
        for item in batch:
            lines.append(json.dumps({"index": {"_index": index, "_id": item["chunk_id"]}}, separators=(",", ":")))
            lines.append(json.dumps({k: item[k] for k in (
                "chunk_id", "doc_id", "source_type", "text", "chunk_index", "char_start", "char_end", "embedding"
            )}, ensure_ascii=False, separators=(",", ":")))
        result = request("POST", "/_bulk", ("\n".join(lines) + "\n").encode(), "application/x-ndjson")
        if result.get("errors"):
            raise RuntimeError(f"bulk errors in {index}")
    request("POST", f"/{index}/_refresh")
    return {
        "index": index, "raw_chunks": len(chunks), "vector_pieces": len(encoded),
        "http400": stats["http400"], "seconds": round(elapsed, 2),
        "pieces_per_second": round(len(encoded) / elapsed, 2),
        "count": request("GET", f"/{index}/_count")["count"],
    }


def main():
    questions = [json.loads(line) for line in open(f"{ROOT}/questions.jsonl", encoding="utf-8")]
    gold = {doc for q in questions for doc in q.get("expected_doc_ids", [])}
    conn = sqlite3.connect(f"{ROOT}/.index_cache/full_es_qwen3_emb/manifest.sqlite3")
    rows = conn.execute("SELECT file_path, doc_id FROM documents WHERE status='chunked' ORDER BY doc_id").fetchall()
    conn.close()
    paths = {doc_id: path for path, doc_id in rows}
    selected = sorted(gold & set(paths))[:1000]
    for _, doc_id in rows:
        if len(selected) >= 1000:
            break
        if doc_id not in selected:
            selected.append(doc_id)
    selected_set = set(selected)
    docs = []
    for doc_id in selected:
        path = os.path.join(ROOT, "corpus/all_documents", paths[doc_id])
        text = open(path, encoding="utf-8", errors="replace").read()
        source = paths[doc_id].split("/", 1)[0]
        docs.append((doc_id, source, text))
    eligible = [q for q in questions if set(q.get("expected_doc_ids", [])) <= selected_set]
    eligible = eligible[:100]
    print(json.dumps({"documents": len(docs), "eligible_questions": len(eligible)}), flush=True)
    results = []
    for size, overlap in VARIANTS:
        results.append(build_variant(docs, size, overlap))
        print(json.dumps(results[-1]), flush=True)
    for result in results:
        hits = 0
        for question in eligible:
            qv = embed_one(question["question"], {"http400": 0})[0][1]
            dense = request("POST", f"/{result['index']}/_search", {
                "size": 30, "_source": ["doc_id"], "query": {"script_score": {
                    "query": {"match_all": {}},
                    "script": {"source": "cosineSimilarity(params.qv, 'embedding') + 1.0", "params": {"qv": qv}},
                }},
            }).get("hits", {}).get("hits", [])
            bm25 = request("POST", f"/{result['index']}/_search", {
                "size": 30, "_source": ["doc_id"], "query": {"match": {"text": {"query": question["question"]}}},
            }).get("hits", {}).get("hits", [])
            ranked = {}
            for rank, hit in enumerate(bm25, 1):
                ranked[hit["_source"]["doc_id"]] = ranked.get(hit["_source"]["doc_id"], 0) + 1 / (60 + rank)
            for rank, hit in enumerate(dense, 1):
                doc_id = hit["_source"]["doc_id"]
                ranked[doc_id] = ranked.get(doc_id, 0) + 1 / (60 + rank)
            top = {doc for doc, _ in sorted(ranked.items(), key=lambda pair: -pair[1])[:30]}
            if top & set(question.get("expected_doc_ids", [])):
                hits += 1
        result["recall_at_30_pct"] = round(hits / len(eligible) * 100, 1) if eligible else None
        print(json.dumps({"index": result["index"], "recall_at_30_pct": result["recall_at_30_pct"]}), flush=True)


if __name__ == "__main__":
    main()
