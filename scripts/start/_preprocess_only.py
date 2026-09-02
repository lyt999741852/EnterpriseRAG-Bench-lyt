"""Preprocess-only entry: chunk the corpus and persist cache+manifest.

No Elasticsearch connection and no embedding calls. Run on the machine that
owns the corpus, then sync the cache dir to the build server.
"""
from __future__ import annotations

import os
import sys

from src.elasticsearch_backend import ElasticsearchConfig  # noqa: F401  (schema reuse)
from src.embedder import EmbedderConfig
from src.indexer import Indexer, IndexerConfig
from src.pipeline import _resolve_path, load_config


def main(config_path: str) -> int:
    cfg = load_config(config_path)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(config_path)))
    pipeline = cfg.get("pipeline", {})
    indexer = Indexer(IndexerConfig(
        corpus_dir=_resolve_path(project_root, cfg["corpus_dir"]),
        chunk_size=cfg["chunking"]["chunk_size"],
        chunk_overlap=cfg["chunking"]["chunk_overlap"],
        embedder=EmbedderConfig(**cfg["embedding"]),
        overwrite=pipeline.get("overwrite_index", False),
        enable_faiss=False,
        enable_bm25=False,
        cache_dir=_resolve_path(project_root, cfg["index_dir"]),
        chunker_version=cfg["chunking"].get("version", "fixed-v2"),
        chunking_method=cfg["chunking"].get("method", "fixed"),
        tokenizer_api_base=cfg["chunking"].get("tokenizer_api_base", ""),
        tokenizer_model_name=cfg["chunking"].get("tokenizer_model_name", ""),
        tokenizer_api_key_env=cfg["chunking"].get("tokenizer_api_key_env", ""),
        tokenizer_timeout=cfg["chunking"].get("tokenizer_timeout", 60),
        tokenizer_local_dir=cfg["chunking"].get("tokenizer_local_dir", ""),
        manifest_enabled=cfg["chunking"].get("manifest_enabled", True),
    ))
    meta = indexer.build()
    print("PREPROCESS_DONE", meta)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.start._preprocess_only configs/xxx.yaml")
        raise SystemExit(1)
    raise SystemExit(main(sys.argv[1]))
