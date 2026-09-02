"""Benchmark embedding throughput: concurrent (8) vs serial, via the real API.

Samples N chunks from a chunks.jsonl and encodes them with
ElasticsearchBackend._encode_batch_with_split against the Conan API.
Usage: python scripts/diag/_bench_embed.py [chunks.jsonl]
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.elasticsearch_backend import ElasticsearchBackend, ElasticsearchConfig
from src.embedder import EmbedderConfig, OpenAICompatibleEmbedder
from src.indexer import Chunk

SAMPLES = 2048


def load_chunks(path: str, n: int):
    chunks = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            row = json.loads(line)
            text = row.get("text", "")
            chunks.append(Chunk(
                chunk_id=row.get("chunk_id", f"bench__chunk{i:05d}"),
                doc_id=row.get("doc_id", f"bench-doc{i}"),
                source_type=row.get("source_type", "bench"),
                text=text,
                char_start=0,
                char_end=len(text),
            ))
            if len(chunks) >= n:
                break
    return chunks


def main() -> int:
    os.environ.setdefault("EMBEDDING_API_KEY", "123456")
    source = sys.argv[1] if len(sys.argv) > 1 else ".index_cache/chunks.jsonl"
    samples = int(sys.argv[2]) if len(sys.argv) > 2 else SAMPLES
    texts = load_chunks(source, samples)
    print(f"loaded {len(texts)} sample chunks from {source}", flush=True)
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
        chunks = list(texts)
        start = time.time()
        pieces, vectors = backend._encode_batch_with_split(embedder, chunks)
        elapsed = time.time() - start
        rate = len(pieces) / elapsed
        print(
            f"concurrency={concurrency}: {len(pieces)} chunks in {elapsed:.1f}s "
            f"-> {rate:.1f} chunks/s (shape={vectors.shape})",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
