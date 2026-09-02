"""Benchmark an embedding configuration on a bounded corpus chunk sample."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import yaml

from .embedder import EmbedderConfig, create_embedder
from .indexer import Indexer, IndexerConfig


def _sample_chunks(corpus_dir: str, chunk_size: int, overlap: int, limit: int):
    indexer = Indexer(IndexerConfig(
        corpus_dir=corpus_dir,
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        enable_bm25=False,
        enable_faiss=False,
        manifest_enabled=False,
    ))
    texts: list[str] = []
    failures = 0
    for source_dir in sorted(Path(corpus_dir).iterdir()):
        if not source_dir.is_dir():
            continue
        for path in source_dir.rglob("*.txt"):
            try:
                document = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                failures += 1
                continue
            for chunk in indexer._chunk_text(document):
                if chunk["text"].strip():
                    texts.append(chunk["text"])
                if len(texts) >= limit:
                    return texts, failures
    return texts, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/full.yaml")
    parser.add_argument("--chunks", type=int, default=10_000)
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    with open(args.config, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    project_root = Path(args.config).resolve().parent.parent
    corpus_dir = Path(config["corpus_dir"])
    if not corpus_dir.is_absolute():
        corpus_dir = project_root / corpus_dir

    texts, read_failures = _sample_chunks(
        str(corpus_dir),
        config["chunking"]["chunk_size"],
        config["chunking"]["chunk_overlap"],
        args.chunks,
    )
    if not texts:
        raise RuntimeError("No chunks were sampled")

    embedder = create_embedder(EmbedderConfig(**config["embedding"]))
    batch_size = max(1, int(config["embedding"].get("batch_size", 256)))
    started = time.perf_counter()
    vector_count = 0
    dimension = 0
    for start in range(0, len(texts), batch_size):
        vectors = embedder.encode(texts[start:start + batch_size])
        vector_count += len(vectors)
        dimension = vectors.shape[1]
    elapsed = time.perf_counter() - started

    report = {
        "provider": config["embedding"]["provider"],
        "model": config["embedding"]["model_name"],
        "chunks": vector_count,
        "dimension": dimension,
        "batch_size": batch_size,
        "elapsed_seconds": round(elapsed, 3),
        "chunks_per_second": round(vector_count / elapsed, 2),
        "read_failures": read_failures,
    }
    try:
        import torch
        if torch.cuda.is_available():
            report["cuda_max_memory_mb"] = round(
                torch.cuda.max_memory_allocated() / 1024 / 1024, 1
            )
    except ImportError:
        pass

    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_suffix(output.suffix + ".tmp")
        temp.write_text(rendered + "\n", encoding="utf-8")
        os.replace(temp, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
