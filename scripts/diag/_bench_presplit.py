"""Benchmark encoding speed on 1200-char-pre-split chunks (no API 400 round trips)."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.elasticsearch_backend import ElasticsearchBackend, ElasticsearchConfig
from src.embedder import EmbedderConfig, OpenAICompatibleEmbedder
from src.indexer import Chunk

SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_sample_v2_chunks.jsonl")
CHAR_CAP = 1200


def pre_split(text):
    """Split text into pieces <= CHAR_CAP chars (whitespace boundaries)."""
    if len(text) <= CHAR_CAP:
        return [text]
    pieces = []
    rest = text
    while len(rest) > CHAR_CAP:
        cut = rest.rfind(" ", 0, CHAR_CAP)
        if cut <= 0:
            cut = CHAR_CAP
        pieces.append(rest[:cut])
        rest = rest[cut:].lstrip()
    if rest:
        pieces.append(rest)
    return pieces


def main() -> int:
    os.environ.setdefault("EMBEDDING_API_KEY", "123456")
    raw = []
    with open(SAMPLE, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= 2048:
                break
            raw.append(json.loads(line).get("text", ""))
    chunks = []
    for i, text in enumerate(raw):
        for j, piece in enumerate(pre_split(text)):
            chunks.append(Chunk(
                chunk_id=f"bench{i:05d}__p{j}",
                doc_id=f"bench-doc{i}",
                source_type="bench",
                text=piece,
                char_start=0,
                char_end=len(piece),
            ))
    print(f"raw={len(raw)} pre-split={len(chunks)} (avg chars={sum(len(c.text) for c in chunks) / len(chunks):.0f})", flush=True)
    embedder = OpenAICompatibleEmbedder(EmbedderConfig(
        provider="openai_compatible",
        model_name="embedding",
        api_base="http://10.72.55.209:7993/v1",
        api_key_env="EMBEDDING_API_KEY",
        device="cpu",
        batch_size=512,
        dimension=1792,
    ))
    for concurrency in (1, 8):
        backend = ElasticsearchBackend(ElasticsearchConfig(
            bulk_size=512, embedding_concurrency=concurrency
        ))
        start = time.time()
        pieces, vectors = backend._encode_batch_with_split(embedder, chunks)
        elapsed = time.time() - start
        print(
            f"concurrency={concurrency}: {len(pieces)} chunks in {elapsed:.1f}s "
            f"-> {len(pieces) / elapsed:.1f} chunks/s (shape={vectors.shape})",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
