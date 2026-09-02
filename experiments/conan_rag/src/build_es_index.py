"""Build or resume an Elasticsearch index without running answer generation."""

from __future__ import annotations

import json
import os
import sys

from .elasticsearch_backend import ElasticsearchBackend, ElasticsearchConfig
from .embedder import EmbedderConfig
from .indexer import Indexer, IndexerConfig
from .pipeline import _resolve_path, load_config


def build(config_path: str) -> dict:
    cfg = load_config(config_path)
    if cfg.get("index_backend") != "elasticsearch":
        raise ValueError("build_es_index requires index_backend: elasticsearch")
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
    preprocess = indexer.build()
    backend = ElasticsearchBackend(ElasticsearchConfig(**cfg["elasticsearch"]))
    health = backend.health()
    stats = backend.index_chunks(
        indexer.chunks,
        indexer.embedder,
        max_chunks=(int(pipeline["max_index_chunks"])
                    if pipeline.get("max_index_chunks") else None),
        progress_path=os.path.join(
            _resolve_path(project_root, cfg["index_dir"]),
            "es_build_progress.json",
        ),
    )
    result = {
        "cluster_status": health.get("status"),
        "embedding": {
            "provider": indexer.config.embedder.provider,
            "model": indexer.config.embedder.model_name,
            "dimension": indexer.embedder.dimension,
            "device": indexer.config.embedder.device,
        },
        "preprocess": preprocess,
        "indexing": stats,
        "es_count": backend.count(),
    }
    report_path = _resolve_path(project_root, cfg["index_dir"])
    os.makedirs(report_path, exist_ok=True)
    report_file = os.path.join(report_path, "es_build_report.json")
    temp_file = f"{report_file}.tmp"
    with open(temp_file, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_file, report_file)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.build_es_index configs/full_es_qwen.yaml")
        raise SystemExit(1)
    build(sys.argv[1])
