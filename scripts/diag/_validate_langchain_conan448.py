"""Validate LangChain recursive 448+32 chunks against Conan on real documents.

Run on the build server after setting EMBEDDING_API_KEY. It only creates a
temporary local token-length cache and never writes an Elasticsearch index.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path
from urllib.error import HTTPError

ROOT = "/opt/enterprise-rag-bench/app"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.indexer import ConanTokenizerLengthCache, _chunk_text_langchain_recursive


DOC_LIMIT = int(os.environ.get("DOC_LIMIT", "1000"))


def main() -> int:
    connection = sqlite3.connect(
        f"{ROOT}/.index_cache/full_es_qwen3_emb/manifest.sqlite3"
    )
    rows = connection.execute(
        "SELECT file_path FROM documents WHERE status='chunked' "
        "ORDER BY doc_id LIMIT ?",
        (DOC_LIMIT,),
    ).fetchall()
    connection.close()
    cache = ConanTokenizerLengthCache(
        Path("/tmp/conan448_validation_tokens.sqlite3"),
        "http://10.72.55.209:7993/v1",
        "embedding",
        "EMBEDDING_API_KEY",
        60,
    )
    try:
        chunks = []
        for (relative_path,) in rows:
            path = os.path.join(ROOT, "corpus/all_documents", relative_path)
            with open(path, encoding="utf-8", errors="replace") as handle:
                chunks.extend(_chunk_text_langchain_recursive(
                    handle.read(), 448, 32, cache
                ))
        lengths = [cache(chunk["text"]) for chunk in chunks]
        http_400 = 0
        for chunk in chunks:
            payload = json.dumps({
                "model": "embedding",
                "input": [chunk["text"]],
                "encoding_format": "float",
            }).encode("utf-8")
            request = urllib.request.Request(
                "http://10.72.55.209:7993/v1/embeddings",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + os.environ["EMBEDDING_API_KEY"],
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=120):
                    pass
            except HTTPError as exc:
                if exc.code == 400:
                    http_400 += 1
                else:
                    raise
        values = sorted(lengths)
        print(json.dumps({
            "documents": len(rows),
            "chunks": len(chunks),
            "over448": sum(value > 448 for value in values),
            "over512": sum(value > 512 for value in values),
            "embedding_http400": http_400,
            "tokens": {
                "p50": values[len(values) // 2],
                "p95": values[int(len(values) * .95)],
                "p99": values[int(len(values) * .99)],
                "max": values[-1],
            },
            "token_cache_entries": cache.connection.execute(
                "SELECT COUNT(*) FROM token_lengths"
            ).fetchone()[0],
        }, ensure_ascii=False, indent=2))
    finally:
        cache.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
