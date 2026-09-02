"""Portable local RAG runner.

The runner deliberately keeps the migration surface small:

    index: corpus -> chunks.jsonl + manifest + optional BM25/FAISS cache
    qa:    questions -> retrieve -> evidence selection -> LLM answers

Paths in the YAML file are resolved relative to the portable_rag directory.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import yaml

from .embedder import EmbedderConfig
from .evaluator import (
    compute_simple_metrics,
    filter_questions_by_source,
    is_failed_answer,
    load_answers_jsonl,
    load_questions,
    validate_answers,
    write_answers_jsonl,
)
from .generator import Generator, GeneratorConfig
from .indexer import Indexer, IndexerConfig
from .llm import LLMConfig
from .retriever import Retriever


def _resolve(root: Path, value: str) -> str:
    path = Path(value)
    return str(path if path.is_absolute() else root / path)


def load_config(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(temp, path)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with open(temp, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(temp, path)


def _build_index(cfg: dict, root: Path) -> tuple[Indexer, dict]:
    retrieval = cfg.get("retrieval", {})
    method = str(retrieval.get("method", "bm25")).lower()
    if method not in {"bm25", "dense", "hybrid"}:
        raise ValueError(f"Unknown retrieval.method: {method}")

    chunking = cfg.get("chunking", {})
    embedding_cfg = EmbedderConfig(**cfg.get("embedding", {}))
    indexer = Indexer(IndexerConfig(
        corpus_dir=_resolve(root, cfg["corpus_dir"]),
        chunk_size=int(chunking.get("chunk_size", 512)),
        chunk_overlap=int(chunking.get("chunk_overlap", 0)),
        embedder=embedding_cfg,
        overwrite=bool(cfg.get("pipeline", {}).get("overwrite_index", False)),
        enable_bm25=method in {"bm25", "hybrid"},
        enable_faiss=method in {"dense", "hybrid"},
        cache_dir=_resolve(root, cfg.get("index_dir", "data/index_cache")),
        chunker_version=str(chunking.get("version", "portable-fixed-v1")),
        chunking_method=str(chunking.get("method", "fixed")),
        tokenizer_api_base=str(chunking.get("tokenizer_api_base", "")),
        tokenizer_model_name=str(chunking.get("tokenizer_model_name", "")),
        tokenizer_api_key_env=str(chunking.get("tokenizer_api_key_env", "")),
        tokenizer_timeout=int(chunking.get("tokenizer_timeout", 60)),
        tokenizer_local_dir=str(chunking.get("tokenizer_local_dir", "")),
        manifest_enabled=bool(chunking.get("manifest_enabled", True)),
    ))
    return indexer, indexer.build()


def _make_generator(cfg: dict) -> Generator:
    generation = cfg.get("generation", {})
    return Generator(GeneratorConfig(
        llm=LLMConfig(**cfg.get("llm", {})),
        max_context_chunks=int(generation.get("max_context_chunks", 5)),
        max_chunks_per_doc=int(generation.get("max_chunks_per_doc", 2)),
        max_document_ids=int(generation.get("max_document_ids", 10)),
        evidence_selection_enabled=bool(
            generation.get("evidence_selection_enabled", False)
        ),
        evidence_selection_candidate_chunks=int(
            generation.get("evidence_selection_candidate_chunks", 10)
        ),
        evidence_selection_max_chunks=int(
            generation.get("evidence_selection_max_chunks", 4)
        ),
        evidence_selection_mode=str(
            generation.get("evidence_selection_mode", "legacy")
        ),
        evidence_selection_fail_closed=bool(
            generation.get("evidence_selection_fail_closed", False)
        ),
        fact_verification_enabled=bool(
            generation.get("fact_verification_enabled", False)
        ),
        final_answer_audit_enabled=bool(
            generation.get("final_answer_audit_enabled", False)
        ),
        adaptive_type_budgets=generation.get("adaptive_type_budgets", {}),
    ))


def run(config_path: str, mode: str | None = None) -> int:
    config_file = Path(config_path).resolve()
    root = config_file.parent.parent
    cfg = load_config(config_file)
    selected_mode = mode or str(cfg.get("pipeline", {}).get("mode", "all"))
    if selected_mode not in {"index", "qa", "all"}:
        raise ValueError("mode must be index, qa, or all")

    indexer, index_meta = _build_index(cfg, root)
    print(
        f"Index ready: {index_meta.get('num_docs', 0)} docs, "
        f"{index_meta.get('num_chunks', 0)} chunks"
    )
    if selected_mode == "index":
        return 0

    questions_path = Path(_resolve(root, cfg["questions_file"]))
    questions = load_questions(str(questions_path))
    pipeline_cfg = cfg.get("pipeline", {})
    questions = filter_questions_by_source(
        questions,
        list(pipeline_cfg.get("source_filter", [])),
        mode=str(pipeline_cfg.get("source_filter_mode", "exact")),
    )
    question_ids = [str(item) for item in pipeline_cfg.get("question_ids", [])]
    if question_ids:
        questions = {qid: questions[qid] for qid in question_ids if qid in questions}
    limit = int(pipeline_cfg.get("question_limit", 0) or 0)
    if limit > 0:
        questions = dict(sorted(questions.items())[:limit])
    if not questions:
        raise ValueError(f"No questions selected from {questions_path}")

    retrieval = cfg.get("retrieval", {})
    method = str(retrieval.get("method", "bm25")).lower()
    embedder = indexer.embedder if method in {"dense", "hybrid"} else None
    retriever = Retriever(
        indexer,
        embedder,
        top_k=int(retrieval.get("top_k", 8)),
        candidate_k=int(retrieval.get("candidate_k", 64)),
        rrf_k=int(retrieval.get("rrf_k", 60)),
        query_prefix=str(cfg.get("embedding", {}).get("query_prefix", "")),
    )
    generator = _make_generator(cfg)

    run_name = str(pipeline_cfg.get("name", "portable_run"))
    output_dir = root / cfg.get("output_dir", "outputs") / run_name
    answers_path = output_dir / "answers.jsonl"
    trace_path = output_dir / "retrieval_trace.jsonl"
    resume = bool(pipeline_cfg.get("resume", True))
    existing = load_answers_jsonl(str(answers_path)) if resume else []
    answers_by_id = {
        row.get("question_id"): row
        for row in existing
        if row.get("question_id") and not is_failed_answer(row)
    }
    traces_by_id: dict[str, dict] = {}
    for qid in sorted(questions):
        if qid in answers_by_id:
            continue
        question = questions[qid]
        query = str(question.get("question", question.get("query", ""))).strip()
        if not query:
            answers_by_id[qid] = {
                "question_id": qid,
                "answer": "[LLM_ERROR: ValueError: empty question]",
                "document_ids": [],
            }
            continue
        if method == "bm25":
            results = retriever.retrieve_bm25(query)
        elif method == "dense":
            results = retriever.retrieve_dense(query)
        else:
            results = retriever.retrieve_hybrid(
                query,
                dense_weight=float(retrieval.get("dense_weight", 0.5)),
                fusion_method=str(retrieval.get("fusion_method", "rrf")),
            )
        reranker = retrieval.get("reranker", {})
        if reranker.get("enabled", False):
            results = retriever.rerank(
                query,
                results,
                model_name=str(reranker["model_name"]),
                top_n=int(reranker.get("top_n", len(results))),
            )
        answer, document_ids = generator.generate_with_sources(
            query, results, question.get("question_type")
        )
        answers_by_id[qid] = {
            "question_id": qid,
            "answer": answer,
            "document_ids": document_ids,
        }
        traces_by_id[qid] = {
            "question_id": qid,
            "query": query,
            "method": retriever.last_retrieval_trace.get("method", method),
            "chunks": [
                {"chunk_id": x.chunk_id, "doc_id": x.doc_id, "score": x.score}
                for x in results
            ],
        }
        print(f"Answered {qid}: {len(results)} retrieved chunks")

    answers = [answers_by_id[qid] for qid in sorted(questions) if qid in answers_by_id]
    traces = [traces_by_id[qid] for qid in sorted(traces_by_id)]
    write_answers_jsonl(answers, str(answers_path))
    _write_jsonl(trace_path, traces)
    errors = validate_answers(answers, set(questions), int(
        cfg.get("generation", {}).get("max_document_ids", 10)
    ))
    _write_json(output_dir / "validation.json", {"valid": not errors, "errors": errors})
    _write_json(output_dir / "simple_metrics.json", compute_simple_metrics(answers, questions))
    print(f"Answers: {answers_path}")
    if errors:
        print(f"Validation errors: {len(errors)}")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", help="portable_rag/configs/config.yaml")
    parser.add_argument("--mode", choices=("index", "qa", "all"))
    args = parser.parse_args()
    return run(args.config, args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
