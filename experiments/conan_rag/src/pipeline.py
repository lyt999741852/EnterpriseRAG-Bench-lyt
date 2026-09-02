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
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
from threading import Lock
from pathlib import Path

import yaml

from .indexer import Indexer, IndexerConfig
from .embedder import EmbedderConfig, create_embedder
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
        chunking_method=cfg["chunking"].get("method", "fixed"),
        tokenizer_api_base=cfg["chunking"].get("tokenizer_api_base", ""),
        tokenizer_model_name=cfg["chunking"].get("tokenizer_model_name", ""),
        tokenizer_api_key_env=cfg["chunking"].get("tokenizer_api_key_env", ""),
        tokenizer_timeout=cfg["chunking"].get("tokenizer_timeout", 60),
        tokenizer_local_dir=cfg["chunking"].get("tokenizer_local_dir", ""),
        manifest_enabled=cfg["chunking"].get("manifest_enabled", True),
    )
    indexer = Indexer(idx_cfg)
    es_backend = None
    read_existing_es = (
        uses_elasticsearch and pipeline.get("read_existing_index", False)
    )
    if read_existing_es:
        # A prebuilt ES evaluation needs the query embedder, but not local
        # chunks.  Skipping Indexer.build() prevents a stale cache fingerprint
        # from triggering a corpus scan or rewriting manifest/chunks metadata.
        es_cfg = ElasticsearchConfig(**cfg.get("elasticsearch", {}))
        es_backend = ElasticsearchBackend(es_cfg)
        print(
            "  Local index build skipped: read-only existing Elasticsearch "
            f"index, count={es_backend.count()}"
        )
    else:
        meta = indexer.build()
        print(f"  Index: {meta['num_chunks']} chunks, {meta['num_docs']} docs")

    # -- Step 2: Retrieve --
    print("\n[2/4] Retrieving...")
    if uses_elasticsearch:
        embedder = indexer.embedder
        if es_backend is None:
            es_cfg = ElasticsearchConfig(**cfg.get("elasticsearch", {}))
            es_backend = ElasticsearchBackend(es_cfg)
        if read_existing_es:
            # Evaluation against a prebuilt index must not mutate it.  This is
            # particularly important when an embedding provider recursively
            # partitions oversized cache chunks into __pN vector documents.
            print(f"  Elasticsearch: read-only existing index, count={es_backend.count()}")
        else:
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
    query_prefix = cfg.get("embedding", {}).get("query_prefix", "")
    retriever = retriever_class(
        retriever_source,
        embedder,
        top_k=retrieval_result_count,
        candidate_k=retrieval_cfg.get(
            "candidate_k", max(100, retrieval_result_count * 10)
        ),
        rrf_k=retrieval_cfg.get("rrf_k", 60),
        query_prefix=query_prefix,
        collapse_recursive_partitions=retrieval_cfg.get(
            "collapse_recursive_partitions", True
        ),
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
        adaptive_type_budgets=generation_cfg.get("adaptive_type_budgets", {}),
    )
    pageindex_cfg = cfg.get("pageindex", {})
    pageindex_enabled_types = {
        str(item) for item in pageindex_cfg.get("enabled_types", [])
        if isinstance(item, str) and item.strip()
    }
    pageindex_router_kwargs = {
        "enabled": pageindex_cfg.get("enabled", False),
        "pageindex_home": _resolve_path(
            project_root, pageindex_cfg.get("home", "vendor/PageIndex")
        ),
        "corpus_dir": _resolve_path(project_root, cfg["corpus_dir"]),
        "manifest_path": _resolve_path(
            project_root,
            pageindex_cfg.get(
                "manifest_path", os.path.join(cfg["index_dir"], "manifest.sqlite3")
            ),
        ),
        "cache_dir": _resolve_path(
            project_root, pageindex_cfg.get("cache_dir", ".pageindex_cache")
        ),
        "min_words": pageindex_cfg.get("min_words", 350),
        "min_headings": pageindex_cfg.get("min_headings", 2),
        "max_candidate_documents": pageindex_cfg.get("max_candidate_documents", 10),
        "max_nodes_per_document": pageindex_cfg.get("max_nodes_per_document", 24),
        "node_preview_chars": pageindex_cfg.get("node_preview_chars", 900),
        "max_followup_queries": pageindex_cfg.get("max_followup_queries", 2),
        "max_hops": pageindex_cfg.get("max_hops", 1),
        "require_node_audit": pageindex_cfg.get("require_node_audit", True),
        "fallback_to_es_on_incomplete": pageindex_cfg.get(
            "fallback_to_es_on_incomplete", True
        ),
        "max_partial_full_document_chars": pageindex_cfg.get(
            "max_partial_full_document_chars", 18000
        ),
        "semantic_event_full_max_chars": pageindex_cfg.get(
            "semantic_event_full_max_chars", 40000
        ),
        "mode_budgets": pageindex_cfg.get("mode_budgets", {}),
    }

    def make_pageindex_router() -> PageIndexHybridRouter:
        # The router records last_trace and lazily owns an LLM client, so a
        # router must never be shared across concurrently processed questions.
        return PageIndexHybridRouter(
            PageIndexRouterConfig(**pageindex_router_kwargs),
            LLMConfig(**cfg["llm"]),
        )

    generator = Generator(gen_cfg)
    pageindex_router = make_pageindex_router()

    qids = sorted(questions.keys())
    total = len(qids)
    answers_path = os.path.join(output_dir, "answers.jsonl")
    run_meta_path = os.path.join(output_dir, "run_meta.json")
    route_trace_path = os.path.join(output_dir, "route_trace.jsonl")
    fingerprint = _run_fingerprint(cfg, qids)

    # Lazy LLM client shared by query rewriting (and anything else cheap)
    _rewrite_llm: "LLMClient | None" = None
    _rewrite_llm_lock = Lock()
    rewrite_cfg = retrieval_cfg.get("query_rewrite", {})
    answer_intent_cfg = retrieval_cfg.get("answer_intent", {})
    answer_intent_quota_cfg = retrieval_cfg.get("answer_intent_quota", {})
    multi_view_cfg = retrieval_cfg.get("multi_view", {})
    semantic_rescue_cfg = retrieval_cfg.get("semantic_rescue", {})
    question_router_cfg = pipeline.get("question_router", {})
    semantic_recall_probe_cfg = pipeline.get("semantic_recall_probe", {})
    question_router_allowed_types = {
        "basic",
        "semantic",
        "intra_document_reasoning",
        "project_related",
        "constrained",
        "conflicting_info",
        "completeness",
        "miscellaneous",
        "high_level",
        "info_not_found",
    }

    def _get_rewrite_llm() -> "LLMClient":
        nonlocal _rewrite_llm
        if _rewrite_llm is None:
            with _rewrite_llm_lock:
                if _rewrite_llm is None:
                    _rewrite_llm = create_llm_client(LLMConfig(**cfg["llm"]))
        return _rewrite_llm

    def _infer_question_type(question: str) -> str | None:
        """Infer routing mode from question text, never from benchmark labels."""
        if not question_router_cfg.get("enabled", False):
            return None
        prompt = (
            "Classify the enterprise question into exactly one retrieval mode. "
            "Use only the question text; do not assume or invent any answer.\n"
            "Choose using these task-shape definitions:\n"
            "- basic: direct fact lookup with recognizable terms, usually one document.\n"
            "- semantic: one standard document, but the question is a verbose paraphrase "
            "with low keyword overlap; answer is one fact or relation. Prefer semantic "
            "for a single scenario even when it contains several qualifiers.\n"
            "- intra_document_reasoning: explicitly combine evidence from different sections "
            "or positions of one long document; a mere sequence or detailed paraphrase is "
            "still semantic.\n"
            "- project_related: connect evidence across multiple projects or documents, "
            "often requiring a causal chain or synthesis.\n"
            "- constrained: distinguish or select among similar candidate documents while "
            "simultaneously satisfying several explicit conditions such as date, region, "
            "product, status or metric. Do not use constrained merely because one question "
            "contains multiple qualifiers.\n"
            "- conflicting_info: reconcile two or more records containing old/new or "
            "contradictory values.\n"
            "- completeness: exhaustive retrieval; asks for all/every/list/count across "
            "multiple records or facts, not merely one representative answer.\n"
            "- miscellaneous: informal or edge content such as Slack memes or hackathon notes.\n"
            "- high_level: broad organization or corpus-level summary.\n"
            "- info_not_found: asks about information that may not exist and should be refused "
            "if unsupported.\n"
            "Allowed modes: basic, semantic, intra_document_reasoning, "
            "project_related, constrained, conflicting_info, completeness, "
            "miscellaneous, high_level, info_not_found.\n"
            "Return JSON only in the form {\"type\":\"...\"}.\n\n"
            f"Question: {question}"
        )
        response = _get_rewrite_llm().generate(
            prompt,
            system_prompt=(
                "You are a routing classifier. Infer the task shape from the "
                "question only. Output valid JSON and no explanation."
            ),
        ).strip()
        try:
            start, end = response.find("{"), response.rfind("}")
            payload = json.loads(response[start:end + 1])
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
        value = payload.get("type") if isinstance(payload, dict) else None
        if not isinstance(value, str):
            return None
        normalized = value.strip().lower().replace("-", "_")
        return normalized if normalized in question_router_allowed_types else None

    def _is_semantic_recall_candidate(
        question: str, routed_type: str | None
    ) -> bool:
        """Conservatively enable semantic retrieval views without changing routing.

        This is deliberately retrieval-only: PageIndex and generation retain the
        primary route.  It addresses questions whose wording is a scenario-level
        paraphrase of a fact in one document, but which a single-label router
        classified as constrained or intra-document reasoning.
        """
        if not semantic_recall_probe_cfg.get("enabled", False):
            return False
        eligible_types = set(
            semantic_recall_probe_cfg.get("eligible_routed_types", [])
        )
        if eligible_types and (routed_type or "unknown") not in eligible_types:
            return False
        prompt = (
            "Decide whether this enterprise question needs an additional "
            "semantic-paraphrase retrieval view. Use only the question text; "
            "do not infer an answer. Return true only when the answer is most "
            "likely a fact, requirement, time window, metric, or procedure in "
            "one document, while the question describes it through a verbose "
            "scenario rather than exact source terminology. Return false for "
            "questions that clearly require exhaustive coverage, reconciliation "
            "of conflicting records, or synthesis across documents. Several "
            "qualifiers alone are not a reason to return false.\n"
            "Return JSON only: {\"semantic_recall_candidate\":true|false}.\n\n"
            f"Question: {question}"
        )
        response = _get_rewrite_llm().generate(
            prompt,
            system_prompt=(
                "You are a conservative retrieval-view classifier. Output valid "
                "JSON and no explanation."
            ),
        ).strip()
        try:
            start, end = response.find("{"), response.rfind("}")
            payload = json.loads(response[start:end + 1])
        except (json.JSONDecodeError, TypeError, ValueError):
            return False
        return bool(
            isinstance(payload, dict)
            and payload.get("semantic_recall_candidate") is True
        )

    def _rewrite_queries(question: str, question_type: str | None) -> list[str]:
        """Generate natural-language semantic retrieval views of a question."""
        max_queries = int(rewrite_cfg.get("max_queries", 2))
        prompt = (
            f"Decompose the enterprise search question below into up to "
            f"natural-language semantic retrieval queries that find the exact "
            f"documents containing the answer.\n"
            f"Make each query cover a different answer facet when the question "
            f"has multiple clauses. Preserve exact named entities, products, "
            f"versions, dates, time windows, quantities, units, thresholds and "
            f"retention periods. Do not turn the output into a bag of keywords, "
            f"and do not remove any hard constraint.\n"
            f"Question type: {question_type or 'unknown'}\n"
            f"Question: {question}\n\n"
            f"Queries:"
        )
        response = _get_rewrite_llm().generate(
            prompt,
            system_prompt=(
                "You produce concise natural-language semantic retrieval "
                "queries. Keep all hard constraints and named entities. "
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

    def _semantic_facet_queries(
        question: str, max_queries: int
    ) -> list[tuple[str, str]]:
        """Plan disjoint evidence facets for a complex semantic question.

        This deliberately produces retrieval queries rather than an answer
        hypothesis.  The facet label survives in the route trace, so each
        retrieved evidence group remains auditable after generation.
        """
        prompt = f"""Decompose the enterprise question below into at most {max_queries}
independent facts that must be evidenced before answering it. Do not answer
the question and do not invent facts.

Keep all constraints needed for one fact together: named entities, product,
region, version/status, date or time window, quantity, unit and threshold.
Do not create a generic topical query and do not split one fact merely because
it has several constraints. Each retrieval query must target one distinct fact
needed by the final answer.

Question: {question}

Return JSON only:
{{"facets":[{{"need":"fact that must be supported","query":"natural-language semantic retrieval query"}}]}}"""
        response = _get_rewrite_llm().generate(
            prompt,
            system_prompt=(
                "You are a conservative enterprise evidence planner. Output "
                "valid JSON only; never answer the user's question."
            ),
        ).strip()
        try:
            start, end = response.find("{"), response.rfind("}")
            payload = json.loads(response[start:end + 1])
        except (json.JSONDecodeError, TypeError, ValueError):
            return []

        raw_facets = payload.get("facets", []) if isinstance(payload, dict) else []
        facets: list[tuple[str, str]] = []
        if not isinstance(raw_facets, list):
            return facets
        for item in raw_facets:
            if not isinstance(item, dict):
                continue
            need = item.get("need")
            query = item.get("query")
            if not isinstance(need, str) or not isinstance(query, str):
                continue
            need, query = need.strip(), query.strip()
            if len(need) < 3 or len(query) < 3:
                continue
            pair = (need, query)
            if pair not in facets:
                facets.append(pair)
            if len(facets) >= max_queries:
                break
        return facets

    def _answer_intent_queries(
        self_question: str, question_type: str | None
    ) -> list[str]:
        """Generate evidence intents without guessing or stating an answer."""
        active_cfg = (
            answer_intent_quota_cfg
            if answer_intent_quota_cfg.get("enabled", False)
            else answer_intent_cfg
        )
        max_queries = int(active_cfg.get("max_queries", 2))
        mode = str(active_cfg.get("mode", "evidence_intent"))
        if mode == "answer_schema":
            prompt = (
                f"For the enterprise question below, write up to {max_queries} "
                "natural-language semantic search queries that describe the "
                "structure and evidence an ideal answer must contain. Describe "
                "the required reasoning steps, fields, evidence types and "
                "relationships, but do not answer the question and never invent "
                "a person, value, date, version, status or conclusion. Preserve "
                "every exact entity and hard qualifier already present in the "
                "question. The query should resemble the language likely used in "
                "an authoritative source passage.\n"
                f"Question type: {question_type or 'unknown'}\n"
                f"Question: {self_question}\n\nAnswer-structure evidence queries:"
            )
            system_prompt = (
                "You plan answer-structure retrieval for enterprise evidence. "
                "Return only semantic search queries, one per line. Never supply "
                "the answer or guess missing facts."
            )
        else:
            prompt = (
                f"For the enterprise question below, describe up to {max_queries} "
                "evidence-finding intents. Do not answer the question and do not "
                "invent values. Each line must be a natural-language semantic search "
                "query describing a fact, event, constraint, timeline, metric, or "
                "document type that must be evidenced. Preserve exact entities, dates, "
                "numbers, versions and qualifiers from the question.\n"
                f"Question type: {question_type or 'unknown'}\n"
                f"Question: {self_question}\n\nEvidence queries:"
            )
            system_prompt = (
                "You are an evidence-intent planner. Return only semantic search "
                "queries, one per line. Never answer the question."
            )
        response = _get_rewrite_llm().generate(
            prompt,
            system_prompt=system_prompt,
        ).strip()
        queries: list[str] = []
        for line in response.splitlines():
            line = line.strip().lstrip("-*0123456789. ").strip()
            if line and len(line) > 3 and line != self_question:
                queries.append(line)
            if len(queries) >= max_queries:
                break
        return queries

    def _rrf_merge(
        result_lists: list[list], top_n: int, rrf_k: int = 60,
        weights: list[float] | None = None,
    ) -> list:
        """Fuse ranked chunk lists with weighted reciprocal-rank fusion."""
        seen: dict[str, object] = {}
        scores: dict[str, float] = {}
        for list_index, results in enumerate(result_lists):
            weight = weights[list_index] if weights and list_index < len(weights) else 1.0
            for rank, result in enumerate(results, 1):
                chunk_id = result.chunk_id
                if chunk_id not in seen:
                    seen[chunk_id] = result
                scores[chunk_id] = scores.get(chunk_id, 0.0) + (
                    weight / (rrf_k + rank)
                )
        ordered = sorted(scores, key=lambda chunk_id: -scores[chunk_id])[:top_n]
        return [seen[chunk_id] for chunk_id in ordered]

    def _merge_evidence_quota(
        base_results: list,
        subquery_results: list[list],
        top_n: int,
        per_query_quota: int,
    ) -> list:
        """Reserve evidence slots for independently reranked semantic facets.

        The primary query keeps most of the context budget.  Each subquery may
        contribute only a small number of chunks, preferring documents not
        already represented in the primary evidence.  This preserves the
        baseline ranking while making multi-facet evidence available to the
        PageIndex and answer stages.
        """
        quota = max(0, int(per_query_quota))
        if not subquery_results or quota == 0:
            return base_results[:top_n]

        base_budget = max(0, top_n - quota * len(subquery_results))
        selected: list = []
        seen_chunks: set[str] = set()
        seen_docs: set[str] = set()

        def add(result) -> bool:
            if result.chunk_id in seen_chunks or len(selected) >= top_n:
                return False
            selected.append(result)
            seen_chunks.add(result.chunk_id)
            seen_docs.add(result.doc_id)
            return True

        for result in base_results[:base_budget]:
            add(result)

        for facet_results in subquery_results:
            added = 0
            # First maximize document coverage, then allow another supporting
            # chunk when that is all the facet can provide.
            for require_new_doc in (True, False):
                for result in facet_results:
                    if added >= quota:
                        break
                    if require_new_doc and result.doc_id in seen_docs:
                        continue
                    if add(result):
                        added += 1
                if added >= quota:
                    break

        for result in base_results:
            if len(selected) >= top_n:
                break
            add(result)
        return selected

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
    if resume and os.path.exists(route_trace_path):
        for item in load_answers_jsonl(route_trace_path):
            qid = item.get("question_id")
            if qid in questions:
                route_traces_by_qid[qid] = item
    checkpoint_interval = max(1, int(pipeline.get("checkpoint_interval", 1)))
    # Operational concurrency is deliberately outside the run fingerprint so
    # a safe capacity adjustment can resume completed answers unchanged.
    question_parallelism = max(
        1, int(os.environ.get(
            "QUESTION_PARALLELISM", pipeline.get("question_parallelism", 1)
        ))
    )
    embedding_parallelism = max(
        1, int(os.environ.get("EMBEDDING_PARALLELISM", "1"))
    )
    dedicated_parallel_embedders = (
        question_parallelism > 1
        and embedder is not None
        and embedding_parallelism >= question_parallelism
    )
    # SentenceTransformers/torch inference is not guaranteed thread-safe on a
    # shared model instance.  Serializing the tiny query-embedding call keeps
    # CPU retrieval deterministic while independent LLM-heavy question flows
    # remain concurrent.
    embedding_lock = None if dedicated_parallel_embedders else Lock()

    def make_retriever(worker_embedder=None):
        return retriever_class(
            retriever_source,
            embedder if worker_embedder is None else worker_embedder,
            top_k=retrieval_result_count,
            candidate_k=retrieval_cfg.get(
                "candidate_k", max(100, retrieval_result_count * 10)
            ),
            rrf_k=retrieval_cfg.get("rrf_k", 60),
            query_prefix=query_prefix,
            collapse_recursive_partitions=retrieval_cfg.get(
                "collapse_recursive_partitions", True
            ),
        )

    def process_question(
        qid: str,
        worker_retriever,
        worker_generator: Generator,
        worker_router: PageIndexHybridRouter,
    ) -> tuple[dict, dict]:
        q = questions[qid]
        query = q["question"]
        # Strict benchmark mode must not expose the gold-side question type to
        # retrieval, PageIndex, or generation.  Keep a separate internal key
        # for config lookups so the normal mode remains byte-for-byte
        # compatible with existing runs.
        question_only = bool(pipeline.get("question_only", False))
        provided_question_type = None if question_only else q.get("question_type")
        inferred_question_type = (
            _infer_question_type(query)
            if question_only and question_router_cfg.get("enabled", False)
            else None
        )
        question_type = inferred_question_type or provided_question_type
        question_type_key = question_type or "unknown"
        semantic_recall_probe = _is_semantic_recall_candidate(
            query, question_type
        )
        retrieval_type_key = "semantic" if semantic_recall_probe else question_type_key
        semantic_facets: list[dict[str, str]] = []
        answer_intent_trace: dict = {}
        semantic_rescue_trace: dict = {}
        retrieval_stage_trace: dict = {"views": []}

        def summarize_results(items: list) -> dict:
            return {
                "count": len(items),
                "chunk_ids": [getattr(item, "chunk_id", "") for item in items],
                "document_ids": list(dict.fromkeys(
                    getattr(item, "doc_id", "") for item in items
                    if getattr(item, "doc_id", "")
                )),
            }

        def retrieve_view(value: str, view: str) -> list:
            def retrieve() -> list:
                if view == "keyword":
                    return worker_retriever.retrieve_bm25(value)
                if view == "dense":
                    return worker_retriever.retrieve_dense(value)
                if view == "hybrid":
                    return worker_retriever.retrieve_hybrid(
                        value,
                        dense_weight=retrieval_cfg.get("dense_weight", 0.5),
                        fusion_method=retrieval_cfg.get("fusion_method", "rrf"),
                    )
                raise ValueError(f"Unknown retrieval view: {view}")

            if view == "keyword" or embedder is None:
                result = retrieve()
            elif embedding_lock is None:
                result = retrieve()
            else:
                with embedding_lock:
                    result = retrieve()
            stage_trace = getattr(worker_retriever, "last_retrieval_trace", None)
            if isinstance(stage_trace, dict) and stage_trace:
                retrieval_stage_trace["views"].append({
                    "view": view,
                    **stage_trace,
                })
            else:
                retrieval_stage_trace["views"].append({
                    "view": view,
                    **summarize_results(result),
                })
            return result

        def retrieve_original(value: str) -> list:
            if method == "bm25":
                return retrieve_view(value, "keyword")
            if method == "dense":
                return retrieve_view(value, "dense")
            if method == "hybrid":
                return retrieve_view(value, "hybrid")
            raise ValueError(f"Unknown retrieval method: {method}")

        # Multi-view retrieval keeps the original lexical and semantic routes,
        # while rewritten queries are semantic-only. This prevents a natural
        # language rewrite from being treated as an exact keyword query.
        if multi_view_cfg.get("enabled", False):
            routes = multi_view_cfg.get("routes", {})
            default_views = multi_view_cfg.get(
                "default_views", ["original_keyword", "original_dense"]
            )
            views = routes.get(retrieval_type_key, default_views)
            result_lists: list[list] = []
            route_weights: list[float] = []

            def add_view(view_name: str, result_list: list, weight: float = 1.0):
                if result_list:
                    result_lists.append(result_list)
                    route_weights.append(float(weight))

            if "original_keyword" in views:
                add_view(
                    "original_keyword",
                    retrieve_view(query, "keyword"),
                    multi_view_cfg.get("weights", {}).get("original_keyword", 1.2),
                )
            if "original_dense" in views:
                add_view(
                    "original_dense",
                    retrieve_view(query, "dense"),
                    multi_view_cfg.get("weights", {}).get("original_dense", 1.0),
                )
            if "original_hybrid" in views:
                add_view(
                    "original_hybrid",
                    retrieve_original(query),
                    multi_view_cfg.get("weights", {}).get("original_hybrid", 1.0),
                )

            if (
                "rewritten_dense" in views
                and rewrite_cfg.get("enabled", False)
                and retrieval_type_key in rewrite_cfg.get("types", [])
            ):
                try:
                    rewritten = _rewrite_queries(query, retrieval_type_key)
                    for rewritten_query in rewritten:
                        add_view(
                            "rewritten_dense",
                            retrieve_view(rewritten_query, "dense"),
                            multi_view_cfg.get("weights", {}).get(
                                "rewritten_dense", 0.9
                            ),
                        )
                    print(
                        f"  [query_rewrite] {qid}: {len(rewritten)} semantic "
                        "query(s) added"
                    )
                except Exception as exc:  # rewriting is best-effort
                    print(f"  [query_rewrite] skipped {qid}: {exc}")

            if (
                "answer_intent_dense" in views
                and answer_intent_cfg.get("enabled", False)
                and retrieval_type_key in answer_intent_cfg.get("types", [])
            ):
                try:
                    intents = _answer_intent_queries(query, retrieval_type_key)
                    for intent in intents:
                        add_view(
                            "answer_intent_dense",
                            retrieve_view(intent, "dense"),
                            multi_view_cfg.get("weights", {}).get(
                                "answer_intent_dense", 0.4
                            ),
                        )
                    print(
                        f"  [answer_intent] {qid}: {len(intents)} semantic "
                        "evidence-intent query(s) added"
                    )
                except Exception as exc:  # intent planning is best-effort
                    print(f"  [answer_intent] skipped {qid}: {exc}")

            results = _rrf_merge(
                result_lists,
                retrieval_result_count if reranker_enabled else top_k,
                rrf_k=retrieval_cfg.get("rrf_k", 60),
                weights=route_weights,
            ) if result_lists else retrieve_original(query)
        else:
            results = retrieve_original(query)

        def retrieve_query(value: str) -> list:
            # PageIndex follow-up searches use the stable original hybrid route;
            # recursively expanding every follow-up would multiply LLM calls.
            return retrieve_original(value)

        def rerank_candidates(
            search_query: str, candidates: list, final_top_n: int
        ) -> list:
            if not reranker_enabled or not candidates:
                return candidates
            rerank_kwargs = {
                "model_name": reranker_cfg.get("model_name", ""),
                "top_n": final_top_n,
            }
            if uses_elasticsearch:
                rerank_kwargs.update({
                    "api_base": reranker_cfg.get("api_base", ""),
                    "api_key_env": reranker_cfg.get("api_key_env", ""),
                    "timeout": reranker_cfg.get("timeout", 120),
                })
            return worker_retriever.rerank(
                search_query, candidates, **rerank_kwargs
            )

        rerank_top_n = int(reranker_cfg.get("top_n", top_k))
        pre_rerank = list(results)
        results = rerank_candidates(query, results, rerank_top_n)
        retrieval_stage_trace["rerank"] = {
            "enabled": bool(reranker_enabled),
            "before": summarize_results(pre_rerank),
            "after": summarize_results(results),
        }

        if semantic_rescue_cfg.get("enabled", False) and reranker_enabled:
            # Retrieval-conditioned rescue deliberately does not alter the primary
            # route.  A document is eligible only when two independently planned
            # semantic views both surface it near the top, then the original query
            # reranker confirms its relevance.  This avoids trying to predict the
            # benchmark's latent "semantic" label from question text.
            try:
                rewrite_queries = _rewrite_queries(query, "semantic_evidence")[:max(
                    0, int(semantic_rescue_cfg.get("rewrite_queries", 1))
                )]
                intent_queries = _answer_intent_queries(
                    query, "semantic_evidence"
                )[:max(0, int(semantic_rescue_cfg.get("intent_queries", 1)))]
                rescue_queries = [
                    ("rewrite", value) for value in rewrite_queries
                ] + [
                    ("answer_intent", value) for value in intent_queries
                ]
                per_view_top_n = max(
                    1, int(semantic_rescue_cfg.get("per_view_top_n", 8))
                )
                consensus_top_docs = max(
                    1, int(semantic_rescue_cfg.get("consensus_top_docs", 2))
                )
                rescue_groups: list[tuple[str, str, list]] = []
                for view_name, rescue_query in rescue_queries:
                    group = rerank_candidates(
                        query,
                        retrieve_view(rescue_query, "dense"),
                        per_view_top_n,
                    )
                    rescue_groups.append((view_name, rescue_query, group))

                def top_documents(items: list, limit: int) -> list[str]:
                    documents: list[str] = []
                    for item in items:
                        if item.doc_id and item.doc_id not in documents:
                            documents.append(item.doc_id)
                        if len(documents) >= limit:
                            break
                    return documents

                grouped_docs = [
                    set(top_documents(group, consensus_top_docs))
                    for _, _, group in rescue_groups
                    if group
                ]
                shared_docs = (
                    set.intersection(*grouped_docs) if len(grouped_docs) >= 2
                    else set()
                )
                anchor_doc_count = max(
                    0, int(semantic_rescue_cfg.get("base_anchor_docs", 8))
                )
                anchor_docs = set(top_documents(results, anchor_doc_count))
                eligible_docs = shared_docs - anchor_docs

                def document_rank(doc_id: str) -> int:
                    score = 0
                    for _, _, group in rescue_groups:
                        for rank, item in enumerate(group, 1):
                            if item.doc_id == doc_id:
                                score += rank
                                break
                    return score

                max_rescue_docs = max(
                    0, int(semantic_rescue_cfg.get("max_rescue_docs", 1))
                )
                selected_docs = sorted(eligible_docs, key=document_rank)[:max_rescue_docs]
                rescue_items: list = []
                seen_rescue_chunks: set[str] = set()
                for doc_id in selected_docs:
                    candidates = [
                        item
                        for _, _, group in rescue_groups
                        for item in group
                        if item.doc_id == doc_id and item.chunk_id not in seen_rescue_chunks
                    ]
                    if candidates:
                        best = max(candidates, key=lambda item: item.score)
                        rescue_items.append(best)
                        seen_rescue_chunks.add(best.chunk_id)

                if rescue_items:
                    insertion_after = max(
                        0, int(semantic_rescue_cfg.get("insertion_after_chunks", 8))
                    )
                    base_budget = max(0, rerank_top_n - len(rescue_items))
                    prefix = results[:min(insertion_after, base_budget)]
                    suffix = results[len(prefix):base_budget]
                    results = prefix + rescue_items + suffix
                semantic_rescue_trace = {
                    "queries": [
                        {"view": view, "query": rescue_query}
                        for view, rescue_query, _ in rescue_groups
                    ],
                    "top_document_ids": {
                        view: top_documents(group, consensus_top_docs)
                        for view, _, group in rescue_groups
                    },
                    "shared_document_ids": sorted(shared_docs),
                    "anchor_document_ids": sorted(anchor_docs),
                    "rescued_document_ids": [item.doc_id for item in rescue_items],
                    "rescued_chunk_ids": [item.chunk_id for item in rescue_items],
                }
                if rescue_items:
                    print(
                        f"  [semantic_rescue] {qid}: {len(rescue_items)} "
                        "consensus document(s) inserted"
                    )
            except Exception as exc:  # rescue must never interrupt baseline retrieval
                semantic_rescue_trace = {"error": str(exc)}
                print(f"  [semantic_rescue] skipped {qid}: {exc}")

        if (
            answer_intent_quota_cfg.get("enabled", False)
            and retrieval_type_key in answer_intent_quota_cfg.get("types", [])
            and reranker_enabled
        ):
            try:
                intents = _answer_intent_queries(query, retrieval_type_key)
                intent_top_n = max(
                    1, int(answer_intent_quota_cfg.get("per_query_top_n", 10))
                )
                intent_groups = [
                    rerank_candidates(
                        intent,
                        retrieve_view(intent, "dense"),
                        intent_top_n,
                    )
                    for intent in intents
                ]
                base_chunk_ids = {item.chunk_id for item in results}
                merged = _merge_evidence_quota(
                    results,
                    intent_groups,
                    rerank_top_n,
                    int(answer_intent_quota_cfg.get("per_query_quota", 3)),
                )
                contributed = [
                    item for item in merged if item.chunk_id not in base_chunk_ids
                ]
                answer_intent_trace = {
                    "queries": intents,
                    "contributed_chunk_ids": [item.chunk_id for item in contributed],
                    "contributed_document_ids": list(dict.fromkeys(
                        item.doc_id for item in contributed
                    )),
                }
                results = merged
                print(
                    f"  [answer_intent_quota] {qid}: {len(intents)} query(s), "
                    f"{len(contributed)} new chunk(s) reserved"
                )
            except Exception as exc:  # intent planning is best-effort
                answer_intent_trace = {"error": str(exc)}
                print(f"  [answer_intent_quota] skipped {qid}: {exc}")

        semantic_quota_cfg = retrieval_cfg.get("semantic_evidence_quota", {})
        if (
            semantic_quota_cfg.get("enabled", False)
            and retrieval_type_key in semantic_quota_cfg.get("types", [])
            and reranker_enabled
        ):
            try:
                facet_pairs = _semantic_facet_queries(
                    query,
                    max(1, int(semantic_quota_cfg.get("max_queries", 2))),
                )
                semantic_facets = [
                    {"need": need, "query": facet_query}
                    for need, facet_query in facet_pairs
                ]
                facet_top_n = max(
                    1, int(semantic_quota_cfg.get("per_query_top_n", 8))
                )
                facet_results = [
                    rerank_candidates(
                        facet_query,
                        retrieve_view(facet_query, "dense"),
                        facet_top_n,
                    )
                    for _, facet_query in facet_pairs
                ]
                results = _merge_evidence_quota(
                    results,
                    facet_results,
                    rerank_top_n,
                    int(semantic_quota_cfg.get("per_query_quota", 3)),
                )
                print(
                    f"  [semantic_quota] {qid}: {len(facet_results)} facet "
                    "query(s) reserved after rerank"
                )
            except Exception as exc:  # facet routing is best-effort
                print(f"  [semantic_quota] skipped {qid}: {exc}")

        expansion_cfg = retrieval_cfg.get("parent_expansion", {})
        if expansion_cfg.get("enabled", False):
            if uses_elasticsearch:
                raise ValueError(
                    "ES neighbor expansion is not enabled yet; "
                    "set retrieval.parent_expansion.enabled=false"
                )
            results = worker_retriever.expand_neighbors(
                results,
                neighbor_chunks=expansion_cfg.get("neighbor_chunks", 1),
            )

        use_pageindex = (
            not pageindex_enabled_types
            or question_type_key in pageindex_enabled_types
        )
        if use_pageindex:
            results = worker_router.route(
                query,
                question_type,
                results,
                retrieve_callback=retrieve_query,
            )
            route_trace = {
                "question_id": qid,
                **worker_router.last_trace,
            }
        else:
            route_trace = {
                "question_id": qid,
                "initial_chunks": len(results),
                "initial_documents": len({item.doc_id for item in results}),
                "route_action": "pageindex_bypassed_type",
                "pageindex_enabled_types": sorted(pageindex_enabled_types),
            }
        if semantic_facets:
            route_trace["semantic_facets"] = semantic_facets
        if answer_intent_trace:
            route_trace["answer_intent_quota"] = answer_intent_trace
        if semantic_rescue_trace:
            route_trace["semantic_rescue"] = semantic_rescue_trace
        retrieval_stage_trace["final_before_generation"] = summarize_results(results)
        route_trace["retrieval_stages"] = retrieval_stage_trace
        route_trace["question_type_source"] = (
            "llm_inferred" if inferred_question_type else (
                "benchmark_metadata" if provided_question_type else "none"
            )
        )
        if inferred_question_type:
            route_trace["inferred_question_type"] = inferred_question_type
        if semantic_recall_probe:
            route_trace["semantic_recall_probe"] = {
                "enabled": True,
                "retrieval_type": retrieval_type_key,
                "primary_question_type": question_type_key,
            }

        # Generate
        answer, doc_ids = worker_generator.generate_with_sources(
            query, results, question_type
        )
        return {
            "question_id": qid,
            "answer": answer,
            "document_ids": doc_ids,
        }, route_trace

    pending_qids = [
        qid for qid in qids
        if qid not in answers_by_qid or is_failed_answer(answers_by_qid[qid])
    ]

    def checkpoint_answers() -> None:
        checkpoint = [answers_by_qid[x] for x in qids if x in answers_by_qid]
        write_answers_jsonl(checkpoint, answers_path)
        _write_jsonl_atomic(
            route_trace_path,
            [route_traces_by_qid[x] for x in qids if x in route_traces_by_qid],
        )

    def record_result(qid: str, answer_item: dict, route_trace: dict) -> None:
        nonlocal processed_this_run
        answers_by_qid[qid] = answer_item
        route_traces_by_qid[qid] = route_trace
        processed_this_run += 1

        # Atomic checkpointing prevents a killed process leaving partial JSON.
        if processed_this_run % checkpoint_interval == 0:
            checkpoint_answers()

        completed = sum(
            qid in answers_by_qid and not is_failed_answer(answers_by_qid[qid])
            for qid in qids
        )
        if processed_this_run % 10 == 0 or completed == total:
            elapsed = time.time() - t_start
            rate = processed_this_run / elapsed if elapsed > 0 else 0
            print(f"  [{completed}/{total}] {rate:.1f} q/s -- qid={qid}")

    if question_parallelism == 1:
        for qid in pending_qids:
            answer_item, route_trace = process_question(
                qid, retriever, generator, pageindex_router
            )
            record_result(qid, answer_item, route_trace)
    else:
        print(f"  Answer generation parallelism: {question_parallelism}")
        worker_contexts = None
        if dedicated_parallel_embedders:
            # One model per worker permits concurrent query encoding without
            # invoking the same PyTorch module from multiple threads. Reuse the
            # already loaded model as worker 1 and load the remaining replicas
            # from the local model cache.
            worker_contexts = Queue(maxsize=question_parallelism)
            for worker_index in range(question_parallelism):
                worker_embedder = (
                    embedder if worker_index == 0
                    else create_embedder(idx_cfg.embedder)
                )
                worker_contexts.put((
                    make_retriever(worker_embedder),
                    Generator(gen_cfg),
                    make_pageindex_router(),
                ))
            print(
                "  Query embedding parallelism: "
                f"{question_parallelism} dedicated model instances"
            )

            def process_with_context(qid: str) -> tuple[dict, dict]:
                context = worker_contexts.get()
                try:
                    return process_question(qid, *context)
                finally:
                    worker_contexts.put(context)

        with ThreadPoolExecutor(max_workers=question_parallelism) as pool:
            if worker_contexts is not None:
                futures = {
                    pool.submit(process_with_context, qid): qid
                    for qid in pending_qids
                }
            else:
                futures = {
                    pool.submit(
                        process_question,
                        qid,
                        make_retriever(),
                        Generator(gen_cfg),
                        make_pageindex_router(),
                    ): qid
                    for qid in pending_qids
                }
            for future in as_completed(futures):
                qid = futures[future]
                answer_item, route_trace = future.result()
                record_result(qid, answer_item, route_trace)

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
