"""
Main pipeline orchestrator.
One entry point to run: index -> retrieve -> generate -> evaluate.
"""

from __future__ import annotations

import json
import os
import hashlib
import sys
import time
from pathlib import Path

import yaml

from .indexer import Indexer, IndexerConfig
from .embedder import EmbedderConfig
from .retriever import Retriever
from .elasticsearch_backend import (
    ElasticsearchBackend,
    ElasticsearchConfig,
    ElasticsearchRetriever,
)
from .generator import Generator, GeneratorConfig
from .llm import LLMConfig, create_llm_client
from .pageindex_router import PageIndexHybridRouter, PageIndexRouterConfig
from .evaluator import (
    load_questions,
    filter_questions_by_source,
    is_failed_answer,
    load_answers_jsonl,
    write_answers_jsonl,
    validate_answers,
    run_official_eval,
    compute_simple_metrics,
)


def _resolve_path(base: str, rel: str) -> str:
    """Resolve a path: absolute stays absolute, relative is relative to project root."""
    if os.path.isabs(rel):
        return rel
    return os.path.join(base, rel)


def load_config(config_path: str) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _run_fingerprint(cfg: dict, question_ids: list[str]) -> str:
    payload = {"config": cfg, "question_ids": question_ids}
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json_atomic(path: str, value: dict):
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_path, path)


def _write_jsonl_atomic(path: str, values: list[dict]):
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        for value in values:
            f.write(json.dumps(value, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_path, path)


def run_pipeline(config_path: str) -> int:
    """Main pipeline. Returns 0 on success, 1 on error."""
    # -- Load config --
    cfg = load_config(config_path)
    project_root = os.path.dirname(os.path.abspath(config_path))
    # go up one level (configs/ -> project root)
    project_root = os.path.dirname(project_root)

    pipeline = cfg.get("pipeline", {})
    run_name = pipeline.get("name", "baseline")
    output_dir = os.path.join(
        project_root,
        cfg.get("output_dir", "outputs"),
        run_name,
    )
    os.makedirs(output_dir, exist_ok=True)

    print(f"=" * 60)
    print(f"Pipeline: {run_name}")
    print(f"Output:   {output_dir}")
    print(f"=" * 60)

    # -- Load questions --
    questions_file = _resolve_path(project_root, cfg["questions_file"])
    all_questions = load_questions(questions_file)
    print(f"\nLoaded {len(all_questions)} questions from {questions_file}")

    source_filter = pipeline.get("source_filter", [])
    source_filter_mode = pipeline.get("source_filter_mode", "exact")
    questions = filter_questions_by_source(
        all_questions, source_filter, mode=source_filter_mode
    )
    selected_question_ids = pipeline.get("question_ids", [])
    if selected_question_ids:
        missing = [qid for qid in selected_question_ids if qid not in questions]
        if missing:
            raise ValueError(f"Unknown or filtered question_ids: {missing}")
        questions = {qid: questions[qid] for qid in selected_question_ids}
    question_limit = int(pipeline.get("question_limit", 0) or 0)
    if question_limit > 0:
        questions = dict(list(sorted(questions.items()))[:question_limit])
    print(
        f"After source filter {source_filter} ({source_filter_mode}): "
        f"{len(questions)} questions"
    )
    if not questions:
        print("No questions match the filter. Exiting.")
        return 1

    # -- Step 1: Index --
    print("\n[1/4] Building index...")
    retrieval_cfg = cfg["retrieval"]  # need early for enable_faiss decision
    backend_type = cfg.get("index_backend", "local")
    if backend_type not in ("local", "elasticsearch"):
        raise ValueError(f"Unknown index_backend: {backend_type}")
    uses_elasticsearch = backend_type == "elasticsearch"
    needs_faiss = not uses_elasticsearch and retrieval_cfg["method"] in ("dense", "hybrid")
    needs_bm25 = not uses_elasticsearch and retrieval_cfg["method"] in ("bm25", "hybrid")
    idx_cfg = IndexerConfig(
        corpus_dir=_resolve_path(project_root, cfg["corpus_dir"]),
        chunk_size=cfg["chunking"]["chunk_size"],
        chunk_overlap=cfg["chunking"]["chunk_overlap"],
        embedder=EmbedderConfig(**cfg["embedding"]),
        overwrite=pipeline.get("overwrite_index", False),
        enable_faiss=needs_faiss,
        enable_bm25=needs_bm25,
        cache_dir=(
            _resolve_path(project_root, cfg["index_dir"])
            if cfg.get("index_dir") else None
        ),
        chunker_version=cfg["chunking"].get("version", "fixed-v2"),
        manifest_enabled=cfg["chunking"].get("manifest_enabled", True),
    )
    indexer = Indexer(idx_cfg)
    meta = indexer.build()
    print(f"  Index: {meta['num_chunks']} chunks, {meta['num_docs']} docs")

    # -- Step 2: Retrieve --
    print("\n[2/4] Retrieving...")
    if uses_elasticsearch:
        embedder = indexer.embedder
        es_cfg = ElasticsearchConfig(**cfg.get("elasticsearch", {}))
        es_backend = ElasticsearchBackend(es_cfg)
        index_stats = es_backend.index_chunks(
            indexer.chunks,
            embedder,
            max_chunks=(int(pipeline["max_index_chunks"])
                        if pipeline.get("max_index_chunks") else None),
        )
        print(f"  Elasticsearch: {json.dumps(index_stats, ensure_ascii=False)}")
    elif needs_faiss:
        # Reuse the model that built the index; loading a second copy can
        # otherwise double CPU/GPU memory usage.
        embedder = indexer.embedder
    else:
        embedder = None  # not needed for BM25
    method = retrieval_cfg["method"]
    top_k = retrieval_cfg["top_k"]
    reranker_cfg = retrieval_cfg.get("reranker", {})
    reranker_enabled = reranker_cfg.get("enabled", False)
    retrieval_result_count = (
        reranker_cfg.get("candidate_k", max(30, top_k))
        if reranker_enabled else top_k
    )

    retriever_class = ElasticsearchRetriever if uses_elasticsearch else Retriever
    retriever_source = es_backend if uses_elasticsearch else indexer
    retriever = retriever_class(
        retriever_source,
        embedder,
        top_k=retrieval_result_count,
        candidate_k=retrieval_cfg.get(
            "candidate_k", max(100, retrieval_result_count * 10)
        ),
        rrf_k=retrieval_cfg.get("rrf_k", 60),
    )

    # -- Step 3: Generate --
    print("\n[3/4] Generating answers...")
    generation_cfg = cfg.get("generation", {})
    gen_cfg = GeneratorConfig(
        llm=LLMConfig(**cfg["llm"]),
        max_context_chunks=generation_cfg.get("max_context_chunks", 5),
        max_chunks_per_doc=generation_cfg.get("max_chunks_per_doc", 2),
        max_document_ids=generation_cfg.get("max_document_ids", 10),
        evidence_selection_enabled=generation_cfg.get(
            "evidence_selection_enabled", False
        ),
        evidence_selection_candidate_chunks=generation_cfg.get(
            "evidence_selection_candidate_chunks", 10
        ),
        evidence_selection_max_chunks=generation_cfg.get(
            "evidence_selection_max_chunks", 4
        ),
        evidence_selection_mode=generation_cfg.get(
            "evidence_selection_mode", "legacy"
        ),
        evidence_selection_anchor_chunks=generation_cfg.get(
            "evidence_selection_anchor_chunks", 0
        ),
        evidence_selection_fallback_chunks=generation_cfg.get(
            "evidence_selection_fallback_chunks", 2
        ),
        fact_verification_enabled=generation_cfg.get(
            "fact_verification_enabled", False
        ),
        evidence_selection_fail_closed=generation_cfg.get(
            "evidence_selection_fail_closed", False
        ),
        final_answer_audit_enabled=generation_cfg.get(
            "final_answer_audit_enabled", False
        ),
    )
    generator = Generator(gen_cfg)

    pageindex_cfg = cfg.get("pageindex", {})
    pageindex_router = PageIndexHybridRouter(
        PageIndexRouterConfig(
            enabled=pageindex_cfg.get("enabled", False),
            pageindex_home=_resolve_path(
                project_root, pageindex_cfg.get("home", "vendor/PageIndex")
            ),
            corpus_dir=_resolve_path(project_root, cfg["corpus_dir"]),
            manifest_path=_resolve_path(
                project_root,
                pageindex_cfg.get(
                    "manifest_path", os.path.join(cfg["index_dir"], "manifest.sqlite3")
                ),
            ),
            cache_dir=_resolve_path(
                project_root, pageindex_cfg.get("cache_dir", ".pageindex_cache")
            ),
            min_words=pageindex_cfg.get("min_words", 350),
            min_headings=pageindex_cfg.get("min_headings", 2),
            max_candidate_documents=pageindex_cfg.get(
                "max_candidate_documents", 10
            ),
            max_nodes_per_document=pageindex_cfg.get(
                "max_nodes_per_document", 24
            ),
            node_preview_chars=pageindex_cfg.get("node_preview_chars", 900),
            max_followup_queries=pageindex_cfg.get("max_followup_queries", 2),
            max_hops=pageindex_cfg.get("max_hops", 1),
            require_node_audit=pageindex_cfg.get("require_node_audit", True),
            fallback_to_es_on_incomplete=pageindex_cfg.get(
                "fallback_to_es_on_incomplete", True
            ),
            max_partial_full_document_chars=pageindex_cfg.get(
                "max_partial_full_document_chars", 18000
            ),
            semantic_event_full_max_chars=pageindex_cfg.get(
                "semantic_event_full_max_chars", 40000
            ),
        ),
        LLMConfig(**cfg["llm"]),
    )

    qids = sorted(questions.keys())
    total = len(qids)
    answers_path = os.path.join(output_dir, "answers.jsonl")
    run_meta_path = os.path.join(output_dir, "run_meta.json")
    route_trace_path = os.path.join(output_dir, "route_trace.jsonl")
    fingerprint = _run_fingerprint(cfg, qids)

    # Lazy LLM client shared by query rewriting (and anything else cheap)
    _rewrite_llm: "LLMClient | None" = None
    rewrite_cfg = retrieval_cfg.get("query_rewrite", {})

    def _get_rewrite_llm() -> "LLMClient":
        nonlocal _rewrite_llm
        if _rewrite_llm is None:
            _rewrite_llm = create_llm_client(LLMConfig(**cfg["llm"]))
        return _rewrite_llm

    def _rewrite_queries(question: str, question_type: str | None) -> list[str]:
        """Ask the LLM for 1-2 concise search queries capturing the core
        entities/topic of a detail-heavy question."""
        max_queries = int(rewrite_cfg.get("max_queries", 2))
        prompt = (
            f"Rewrite the enterprise search question below into up to "
            f"{max_queries} concise search queries that would find the exact "
            f"documents containing the answer.\n"
            f"Include: named entities (people, companies, products, services), "
            f"document/topic keywords, and the core subject. Remove qualifiers, "
            f"examples, numbers-as-limits and filler words.\n"
            f"Question type: {question_type or 'unknown'}\n"
            f"Question: {question}\n\n"
            f"Queries:"
        )
        response = _get_rewrite_llm().generate(
            prompt,
            system_prompt=(
                "You rewrite search questions into concise keyword queries. "
                "Output ONLY the queries, one per line, no numbering, "
                "no explanation, no extra text."
            ),
        ).strip()
        queries: list[str] = []
        for ln in response.splitlines():
            ln = ln.strip().lstrip("-*0123456789. ").strip()
            if ln and len(ln) > 3 and ln != question:
                queries.append(ln)
            if len(queries) >= max_queries:
                break
        return queries

    def _rrf_merge(
        result_lists: list[list], top_n: int, rrf_k: int = 60
    ) -> list:
        """Fuse multiple ranked result lists by doc_id using reciprocal-rank
        fusion, preserving the first-seen RetrieveResult object."""
        seen: dict[str, object] = {}
        scores: dict[str, float] = {}
        for results in result_lists:
            for rank, result in enumerate(results, 1):
                doc_id = result.doc_id
                if doc_id not in seen:
                    seen[doc_id] = result
                scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (rrf_k + rank)
        ordered = sorted(scores, key=lambda d: -scores[d])[:top_n]
        return [seen[d] for d in ordered]

    answers_by_qid: dict[str, dict] = {}
    resume = pipeline.get("resume", True)
    resume_legacy = pipeline.get("resume_legacy", False)
    if resume and os.path.exists(answers_path):
        previous_meta = {}
        if os.path.exists(run_meta_path):
            with open(run_meta_path, encoding="utf-8") as f:
                previous_meta = json.load(f)
        compatible = previous_meta.get("fingerprint") == fingerprint
        if compatible or (resume_legacy and not previous_meta):
            for item in load_answers_jsonl(answers_path):
                qid = item.get("question_id")
                if qid in questions:
                    answers_by_qid[qid] = item
            successful = sum(
                not is_failed_answer(item) for item in answers_by_qid.values()
            )
            print(
                f"  Resume checkpoint: {successful} successful answers kept; "
                f"failed answers will be retried"
            )
        else:
            print("  Existing answers ignored because the run fingerprint changed")

    _write_json_atomic(run_meta_path, {
        "fingerprint": fingerprint,
        "config_path": os.path.abspath(config_path),
        "question_count": total,
    })

    t_start = time.time()
    processed_this_run = 0
    route_traces_by_qid: dict[str, dict] = {}
    checkpoint_interval = max(1, int(pipeline.get("checkpoint_interval", 1)))
    for i, qid in enumerate(qids):
        existing = answers_by_qid.get(qid)
        if existing is not None and not is_failed_answer(existing):
            continue
        q = questions[qid]
        query = q["question"]

        def retrieve_query(value: str) -> list:
            if method == "bm25":
                return retriever.retrieve_bm25(value)
            if method == "dense":
                return retriever.retrieve_dense(value)
            if method == "hybrid":
                return retriever.retrieve_hybrid(
                    value,
                    dense_weight=retrieval_cfg.get("dense_weight", 0.5),
                    fusion_method=retrieval_cfg.get("fusion_method", "rrf"),
                )
            raise ValueError(f"Unknown retrieval method: {method}")

        # Retrieve
        results = retrieve_query(query)

        # Optional LLM query rewriting: re-run retrieval on rewritten queries
        # and fuse candidates for detail-heavy question types that suffer from
        # low recall (e.g. long semantic/basic questions).
        if (
            rewrite_cfg.get("enabled", False)
            and q.get("question_type") in rewrite_cfg.get("types", [])
        ):
            try:
                rewritten = _rewrite_queries(query, q.get("question_type"))
                extra_lists: list[list] = []
                for rq in rewritten:
                    extra_lists.append(retrieve_query(rq))
                if extra_lists:
                    results = _rrf_merge([results] + extra_lists, top_k)
                    print(
                        f"  [query_rewrite] {qid}: {len(rewritten)} query(s) "
                        f"fused -> {len(results)} candidates"
                    )
            except Exception as exc:  # rewriting is best-effort
                print(f"  [query_rewrite] skipped {qid}: {exc}")

        if reranker_enabled:
            if uses_elasticsearch:
                raise ValueError(
                    "ES reranking is not enabled yet; set retrieval.reranker.enabled=false"
                )
            results = retriever.rerank(
                query,
                results,
                model_name=reranker_cfg.get("model_name", ""),
                top_n=reranker_cfg.get("top_n", top_k),
            )

        expansion_cfg = retrieval_cfg.get("parent_expansion", {})
        if expansion_cfg.get("enabled", False):
            if uses_elasticsearch:
                raise ValueError(
                    "ES neighbor expansion is not enabled yet; "
                    "set retrieval.parent_expansion.enabled=false"
                )
            results = retriever.expand_neighbors(
                results,
                neighbor_chunks=expansion_cfg.get("neighbor_chunks", 1),
            )

        results = pageindex_router.route(
            query,
            q.get("question_type"),
            results,
            retrieve_callback=retrieve_query,
        )
        route_traces_by_qid[qid] = {
            "question_id": qid,
            **pageindex_router.last_trace,
        }

        # Generate
        answer, doc_ids = generator.generate_with_sources(
            query, results, q.get("question_type")
        )

        answers_by_qid[qid] = {
            "question_id": qid,
            "answer": answer,
            "document_ids": doc_ids,
        }
        processed_this_run += 1

        # Atomic checkpointing prevents a killed process leaving partial JSON.
        if processed_this_run % checkpoint_interval == 0:
            checkpoint = [answers_by_qid[x] for x in qids if x in answers_by_qid]
            write_answers_jsonl(checkpoint, answers_path)
            _write_jsonl_atomic(
                route_trace_path,
                [route_traces_by_qid[x] for x in qids if x in route_traces_by_qid],
            )

        completed = sum(
            qid in answers_by_qid and not is_failed_answer(answers_by_qid[qid])
            for qid in qids
        )
        if processed_this_run % 10 == 0 or completed == total:
            elapsed = time.time() - t_start
            rate = processed_this_run / elapsed if elapsed > 0 else 0
            print(f"  [{completed}/{total}] {rate:.1f} q/s -- qid={qid}")

    # Write answers JSONL
    answers = [answers_by_qid[qid] for qid in qids if qid in answers_by_qid]
    write_answers_jsonl(answers, answers_path)
    _write_jsonl_atomic(
        route_trace_path,
        [route_traces_by_qid[x] for x in qids if x in route_traces_by_qid],
    )
    print(f"\nAnswers written to {answers_path}")

    validation_errors = validate_answers(answers, set(qids))
    validation_path = os.path.join(output_dir, "validation.json")
    _write_json_atomic(validation_path, {
        "valid": not validation_errors,
        "errors": validation_errors,
    })
    if validation_errors:
        print(f"[WARNING] Submission validation failed: {len(validation_errors)} errors")

    # -- Step 4: Evaluate --
    print("\n[4/4] Evaluating...")
    eval_cfg = cfg.get("evaluation", {})

    # Try official eval first
    official_results = {}
    if not validation_errors and eval_cfg.get("enabled", True):
        official_results = run_official_eval(
            questions_file=questions_file,
            answers_file=answers_path,
            output_dir=output_dir,
            no_correction=eval_cfg.get("no_correction", True),
            parallelism=eval_cfg.get("parallelism", 8),
            timeout=eval_cfg.get("timeout", 3600),
            resume=eval_cfg.get("resume", True),
        )
    elif validation_errors:
        print("Official evaluation skipped until all answers pass validation")

    # Also compute simple metrics (no LLM needed)
    simple = compute_simple_metrics(answers, all_questions)
    simple_path = os.path.join(output_dir, "simple_metrics.json")
    with open(simple_path, "w", encoding="utf-8") as f:
        json.dump(simple, f, indent=2, ensure_ascii=False)
    print(f"Simple metrics written to {simple_path}")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Pipeline complete: {run_name}")
    print(f"  Questions processed: {total}")
    if official_results:
        stats = official_results.get("aggregate_stats", {})
        print(f"  Combined score:       {stats.get('combined_correctness_completeness_score', 'N/A')}")
        print(f"  Avg correctness:      {stats.get('average_correctness_pct', 'N/A')}")
        print(f"  Avg completeness:     {stats.get('average_completeness_pct', 'N/A')}")
    print(f"  Avg recall (simple):  {simple.get('average_recall_pct', 'N/A')}")
    print(f"  Avg invalid docs:     {simple.get('average_invalid_extra_docs', 'N/A')}")
    print(f"{'=' * 60}")

    return 1 if validation_errors else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.pipeline configs/default.yaml")
        sys.exit(1)
    sys.exit(run_pipeline(sys.argv[1]))
