"""End-to-end smoke against the authorized target ES 10.72.100.29:31920 (7.17.8).

Verifies: index creation (1792-dim dense_vector, 16 shards), embedding API,
bulk write, script_score retrieval, and that native knn is rejected (proof
that eval must use dense_mode=script_score).
"""
import json
import os
import sys
import urllib.request
from urllib.error import HTTPError, URLError

ES = "http://10.72.100.29:31920"
INDEX = "enterprise-rag-qwen3-emb-smoke"
EMBED_URL = "http://10.72.55.209:7993/v1/embeddings"
EMBED_KEY = os.environ.get("EMBEDDING_API_KEY", "123456")

TEXTS = [
    "EnterpriseRAG-Bench evaluates retrieval and generation quality on enterprise documents.",
    "The page index navigates long documents with heading-aware chunking.",
    "Elasticsearch 7.17.8 requires script_score for vector similarity search.",
]


def request(method, url, payload=None, headers=None, allowed=None):
    data = None
    req_headers = dict(headers or {})
    if payload is not None:
        if isinstance(payload, str):
            data = payload.encode("utf-8")
        else:
            data = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        if allowed and e.code in allowed:
            return None
        return {"__http_error__": e.code, "body": body[:500]}
    except URLError as e:
        return {"__conn_error__": str(e)}


def main() -> int:
    ok = True

    # 1. Health
    health = request("GET", f"{ES}/_cluster/health")
    print("[1] cluster health:", health.get("status"), "|", health.get("number_of_nodes"), "nodes")
    ok &= health.get("status") in ("green", "yellow")

    # 2. Create index with production-like mapping
    index_def = {
        "settings": {"number_of_shards": 16, "number_of_replicas": 0, "refresh_interval": "30s"},
        "mappings": {"dynamic": "strict", "properties": {
            "chunk_id": {"type": "keyword"},
            "doc_id": {"type": "keyword"},
            "source_type": {"type": "keyword"},
            "text": {"type": "text"},
            "chunk_index": {"type": "integer"},
            "char_start": {"type": "integer"},
            "char_end": {"type": "integer"},
            "embedding_model": {"type": "keyword"},
            "embedding": {"type": "dense_vector", "dims": 1792, "index": True, "similarity": "cosine"},
        }},
    }
    resp = request("PUT", f"{ES}/{INDEX}", index_def, allowed={400, 404})
    if resp is None:
        print("[2] index already exists (400 allowed)")
    elif isinstance(resp, dict) and resp.get("__http_error__"):
        print(f"[2] index create -> HTTP {resp['__http_error__']}: {resp['body'][:200]}")
        ok = False
    else:
        print("[2] index created/acknowledged:", resp.get("acknowledged", resp))

    # 3. Embedding
    emb = request(
        "POST", EMBED_URL,
        {"model": "embedding", "input": TEXTS, "encoding_format": "float"},
        {"Content-Type": "application/json", "Authorization": f"Bearer {EMBED_KEY}"},
    )
    items = sorted(emb.get("data", []), key=lambda x: x.get("index", 0))
    print(f"[3] embedding -> {len(items)} vectors, dim={len(items[0]['embedding']) if items else 0}")
    ok &= len(items) == len(TEXTS)

    # 4. Bulk write
    ops = []
    for i, (text, item) in enumerate(zip(TEXTS, items)):
        ops.append(json.dumps({"index": {"_index": INDEX, "_id": f"smoke__chunk{i:05d}"}}))
        ops.append(json.dumps({
            "chunk_id": f"smoke__chunk{i:05d}", "doc_id": f"smoke-doc{i}",
            "source_type": "smoke", "text": text, "chunk_index": i,
            "embedding_model": "embedding", "embedding": item["embedding"],
        }, ensure_ascii=False))
    bulk = request(
        "POST", f"{ES}/_bulk", "\n".join(ops) + "\n",
        {"Content-Type": "application/x-ndjson"},
    )
    ok &= not bulk.get("errors", True)
    print("[4] bulk -> errors =", bulk.get("errors"))
    request("POST", f"{ES}/{INDEX}/_refresh")
    print("[4b] refreshed")

    # 5. script_score retrieval (the payload eval will use)
    qvec = items[0]["embedding"]
    payload = {
        "size": 5,
        "_source": ["chunk_id", "doc_id", "source_type", "text", "chunk_index"],
        "query": {"script_score": {
            "query": {"match_all": {}},
            "script": {"source": "cosineSimilarity(params.qv, 'embedding') + 1.0",
                       "params": {"qv": qvec}},
        }},
    }
    resp = request("POST", f"{ES}/{INDEX}/_search", payload)
    hits = resp.get("hits", {}).get("hits", []) if "hits" in resp else []
    print(f"[5] script_score -> {len(hits)} hits; top={hits[0]['_source']['chunk_id'] if hits else 'NONE'}")
    ok &= len(hits) == len(TEXTS)

    # 6. Native knn must FAIL on 7.17.8 (proves script_score is required)
    resp = request("POST", f"{ES}/{INDEX}/_search", {
        "size": 5,
        "knn": {"field": "embedding", "query_vector": qvec, "k": 5, "num_candidates": 50},
    })
    expected_fail = resp.get("__http_error__") is not None
    print(f"[6] native knn -> expected failure: {expected_fail} "
          f"({resp.get('__http_error__', 'unexpectedly OK')})")
    if not expected_fail:
        ok = False

    print("\nSMOKE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
