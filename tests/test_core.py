from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from src.evaluator import (
    filter_questions_by_source,
    is_failed_answer,
    run_official_eval,
    validate_answers,
)
from src.generator import (
    FINAL_ANSWER_AUDIT_USER_TEMPLATE,
    Generator,
    GeneratorConfig,
)
from src.elasticsearch_backend import (
    ElasticsearchBackend,
    ElasticsearchConfig,
    ElasticsearchRetriever,
)
from src.embedder import EmbedderConfig
from src.indexer import Chunk, Indexer, IndexerConfig
from src.llm import LLMClient, LLMConfig, OpenAICompatibleClient
from src.retriever import RetrieveResult, Retriever
from src.pageindex_router import (
    PAGEINDEX_ADAPTER_VERSION,
    EvidencePlanner,
    NodeSelection,
    PageIndexHybridRouter,
    PageIndexRouterConfig,
    QuestionSearchPlan,
    TextStructureAdapter,
)


class FakeLLM(LLMClient):
    def _call_api(self, prompt: str, system_prompt: str) -> str:
        return "grounded answer"


class SequencedFakeLLM(LLMClient):
    def __init__(self, responses: list[str]):
        super().__init__(LLMConfig(model_name="fake"))
        self.responses = list(responses)

    def _call_api(self, prompt: str, system_prompt: str) -> str:
        return self.responses.pop(0)


class FakeBM25:
    def get_scores(self, _tokens):
        return np.array([3.0, 2.0, 1.0], dtype=np.float32)


class FakeFaiss:
    ntotal = 3

    def search(self, _vector, count):
        indices = np.array([[0, 2, 1][:count]], dtype=np.int64)
        distances = np.array([[0.9, 0.8, 0.7][:count]], dtype=np.float32)
        return distances, indices


class FakeEmbedder:
    config = EmbedderConfig(model_name="fake", dimension=2)

    def encode(self, _texts, show_progress=False):
        return np.array([[1.0, 0.0] for _ in _texts], dtype=np.float32)

    @property
    def dimension(self):
        return 2


class FakeHTTPResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class FakeIndexer:
    def __init__(self):
        self.chunks = [
            Chunk(f"c{i}", f"d{i}", "github", f"text {i}", 0, 6)
            for i in range(3)
        ]
        self._bm25 = FakeBM25()
        self._faiss_index = FakeFaiss()

    @property
    def bm25(self):
        return self._bm25

    @property
    def faiss_index(self):
        return self._faiss_index


class QuestionFilteringTests(unittest.TestCase):
    def test_exact_and_contains_modes_are_distinct(self):
        questions = {
            "only": {"source_types": ["github"]},
            "mixed": {"source_types": ["github", "slack"]},
        }
        self.assertEqual(
            set(filter_questions_by_source(questions, ["github"], "exact")),
            {"only"},
        )
        self.assertEqual(
            set(filter_questions_by_source(questions, ["github"], "contains")),
            {"only", "mixed"},
        )


class AnswerValidationTests(unittest.TestCase):
    def test_error_answers_and_duplicate_documents_are_rejected(self):
        answer = {
            "question_id": "q1",
            "answer": "[LLM_ERROR: timeout]",
            "document_ids": ["d1", "d1"],
        }
        self.assertTrue(is_failed_answer(answer))
        errors = validate_answers([answer], {"q1"})
        self.assertEqual(len(errors), 2)

    def test_official_eval_uses_results_file_contract(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            root = Path(temp)
            script = root / "metrics_based_eval.py"
            script.write_text("# placeholder", encoding="utf-8")

            def fake_run(command, **_kwargs):
                self.assertIn("--results-file", command)
                self.assertNotIn("--output-dir", command)
                results = Path(command[command.index("--results-file") + 1])
                results.write_text('{"aggregate_stats": {}}', encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            with mock.patch(
                "src.evaluator._find_eval_script", return_value=script
            ), mock.patch("src.evaluator.subprocess.run", side_effect=fake_run):
                result = run_official_eval(
                    "questions.jsonl", "answers.jsonl", str(root / "output")
                )
            self.assertEqual(result, {"aggregate_stats": {}})


class RetrievalTests(unittest.TestCase):
    def test_rrf_rewards_candidates_present_in_both_rankings(self):
        retriever = Retriever(
            FakeIndexer(), FakeEmbedder(), top_k=2, candidate_k=3, rrf_k=60
        )
        results = retriever.retrieve_hybrid("query", fusion_method="rrf")
        self.assertEqual(results[0].chunk_id, "c0")
        self.assertEqual(len(results), 2)

    def test_neighbor_expansion_stays_within_parent_document(self):
        indexer = FakeIndexer()
        indexer.chunks[1].doc_id = "d0"
        retriever = Retriever(indexer, None, top_k=2)
        hit = RetrieveResult("c0", "d0", "github", "text 0", 1.0)
        expanded = retriever.expand_neighbors([hit], neighbor_chunks=1)
        self.assertEqual([item.chunk_id for item in expanded], ["c0", "c1"])


class FakeElasticsearchBackend(ElasticsearchBackend):
    def __init__(self, existing=None):
        super().__init__(ElasticsearchConfig(bulk_size=2))
        self.existing = set(existing or [])
        self.bulk_documents = []

    def ensure_index(self, dimension):
        self.dimension = dimension

    def _existing_ids(self, ids):
        return self.existing.intersection(ids)

    def _request(self, method, path, payload=None, **_kwargs):
        if path == "/_bulk":
            lines = payload.strip().splitlines()
            self.bulk_documents.extend(json.loads(line) for line in lines[1::2])
            items = [
                {"index": {"status": 201}}
                for _ in range(len(lines) // 2)
            ]
            return {"errors": False, "items": items}
        if path.endswith("/_refresh"):
            return {}
        raise AssertionError(f"Unexpected request: {method} {path}")


class ElasticsearchBackendTests(unittest.TestCase):
    def test_mget_disables_source_via_query_parameter(self):
        backend = ElasticsearchBackend(ElasticsearchConfig())
        with mock.patch.object(
            backend,
            "_request",
            return_value={"docs": [{"_id": "c1", "found": True}]},
        ) as request:
            self.assertEqual(backend._existing_ids(["c1"]), {"c1"})
        self.assertEqual(
            request.call_args.args[1],
            "/enterprise-rag-bge-small-v1/_mget?_source=false",
        )

    def test_bulk_index_skips_existing_ids_and_writes_vectors(self):
        chunks = [
            Chunk("d1__fixed-v2__chunk00000", "d1", "github", "one", 0, 3),
            Chunk("d2__fixed-v2__chunk00000", "d2", "github", "two", 0, 3),
        ]
        backend = FakeElasticsearchBackend(existing={chunks[0].chunk_id})
        stats = backend.index_chunks(chunks, FakeEmbedder())
        self.assertEqual(stats["existing"], 1)
        self.assertEqual(stats["indexed"], 1)
        self.assertEqual(backend.dimension, 2)
        self.assertEqual(backend.bulk_documents[0]["doc_id"], "d2")
        self.assertEqual(len(backend.bulk_documents[0]["embedding"]), 2)

    def test_es_hybrid_rrf_prioritizes_shared_candidate(self):
        class SearchBackend:
            @staticmethod
            def bm25_search(_query, _size):
                return [
                    {"_id": "shared", "_source": {"chunk_id": "shared", "doc_id": "d1", "source_type": "github", "text": "one"}},
                    {"_id": "lexical", "_source": {"chunk_id": "lexical", "doc_id": "d2", "source_type": "github", "text": "two"}},
                ]

            @staticmethod
            def dense_search(_vector, _size):
                return [
                    {"_id": "dense", "_source": {"chunk_id": "dense", "doc_id": "d3", "source_type": "github", "text": "three"}},
                    {"_id": "shared", "_source": {"chunk_id": "shared", "doc_id": "d1", "source_type": "github", "text": "one"}},
                ]

        retriever = ElasticsearchRetriever(
            SearchBackend(), FakeEmbedder(), top_k=2, candidate_k=2
        )
        results = retriever.retrieve_hybrid("query", dense_weight=0.5)
        self.assertEqual(results[0].chunk_id, "shared")


class GeneratorTests(unittest.TestCase):
    def test_reported_documents_match_selected_context(self):
        generator = Generator(GeneratorConfig(
            llm=LLMConfig(model_name="fake"),
            max_context_chunks=2,
            max_chunks_per_doc=1,
        ))
        generator._llm = FakeLLM(LLMConfig(model_name="fake"))
        retrieved = [
            RetrieveResult("c1", "d1", "github", "one", 3.0),
            RetrieveResult("c2", "d1", "github", "two", 2.0),
            RetrieveResult("c3", "d2", "github", "three", 1.0),
        ]
        answer, doc_ids = generator.generate_with_sources("question", retrieved)
        self.assertEqual(answer, "grounded answer")
        self.assertEqual(doc_ids, ["d1", "d2"])

    def test_evidence_selector_can_keep_a_lower_ranked_passage(self):
        generator = Generator(GeneratorConfig(
            llm=LLMConfig(model_name="fake"),
            max_chunks_per_doc=1,
            evidence_selection_enabled=True,
            evidence_selection_candidate_chunks=3,
            evidence_selection_max_chunks=2,
        ))
        generator._llm = SequencedFakeLLM([
            '{"selected_indices": [3]}',
            "answer from the selected passage",
        ])
        retrieved = [
            RetrieveResult("c1", "d1", "github", "related", 3.0),
            RetrieveResult("c2", "d2", "github", "conflicting", 2.0),
            RetrieveResult("c3", "d3", "github", "direct evidence", 1.0),
        ]
        answer, doc_ids = generator.generate_with_sources("question", retrieved)
        self.assertEqual(answer, "answer from the selected passage")
        self.assertEqual(doc_ids, ["d3"])

    def test_evidence_selector_falls_back_on_malformed_output(self):
        generator = Generator(GeneratorConfig(
            llm=LLMConfig(model_name="fake"),
            evidence_selection_enabled=True,
            evidence_selection_candidate_chunks=3,
            evidence_selection_max_chunks=2,
        ))
        generator._llm = SequencedFakeLLM(["not json", "fallback answer"])
        retrieved = [
            RetrieveResult("c1", "d1", "github", "one", 3.0),
            RetrieveResult("c2", "d2", "github", "two", 2.0),
            RetrieveResult("c3", "d3", "github", "three", 1.0),
        ]
        answer, doc_ids = generator.generate_with_sources("question", retrieved)
        self.assertEqual(answer, "fallback answer")
        self.assertEqual(doc_ids, ["d1", "d2"])

    def test_tiered_selector_unions_facets_supporting_and_recall_anchors(self):
        generator = Generator(GeneratorConfig(
            llm=LLMConfig(model_name="fake"),
            max_chunks_per_doc=1,
            evidence_selection_enabled=True,
            evidence_selection_mode="tiered_v2",
            evidence_selection_candidate_chunks=4,
            evidence_selection_max_chunks=4,
            evidence_selection_anchor_chunks=1,
        ))
        generator._llm = SequencedFakeLLM([
            json.dumps({
                "facets": ["first", "second"],
                "hard_constraints": ["version v2"],
                "direct_indices": [4],
                "supporting_indices": [3],
                "reject_indices": [2],
                "facet_coverage": [
                    {"facet_index": 1, "passage_indices": [4]},
                    {"facet_index": 2, "passage_indices": [3]},
                ],
            }),
            "tiered answer",
        ])
        retrieved = [
            RetrieveResult(f"c{i}", f"d{i}", "github", f"text {i}", 5.0 - i)
            for i in range(1, 5)
        ]
        answer, doc_ids = generator.generate_with_sources("question", retrieved)
        self.assertEqual(answer, "tiered answer")
        self.assertEqual(doc_ids, ["d4", "d3", "d1"])

    def test_tiered_selector_uses_recall_fallback_for_valid_empty_result(self):
        generator = Generator(GeneratorConfig(
            llm=LLMConfig(model_name="fake"),
            evidence_selection_enabled=True,
            evidence_selection_mode="tiered_v2",
            evidence_selection_fallback_chunks=2,
        ))
        generator._llm = SequencedFakeLLM([
            json.dumps({
                "facets": ["fact"],
                "hard_constraints": [],
                "direct_indices": [],
                "supporting_indices": [],
                "reject_indices": [1, 2, 3],
                "facet_coverage": [],
            }),
            "fallback answer",
        ])
        retrieved = [
            RetrieveResult(f"c{i}", f"d{i}", "github", f"text {i}", 4.0 - i)
            for i in range(1, 4)
        ]
        answer, doc_ids = generator.generate_with_sources("question", retrieved)
        self.assertEqual(answer, "fallback answer")
        self.assertEqual(doc_ids, ["d1", "d2"])

    def test_precision_selector_requires_every_facet_and_rejects_conflicts(self):
        complete = json.dumps({
            "facets": [
                {"facet_index": 1, "description": "cause"},
                {"facet_index": 2, "description": "policy"},
            ],
            "accepted_indices": [1, 2, 3],
            "facet_coverage": [
                {"facet_index": 1, "passage_indices": [1]},
                {"facet_index": 2, "passage_indices": [2]},
            ],
            "coverage_complete": True,
            "conflicts": [],
        })
        self.assertEqual(
            Generator._parse_precision_indices(complete, 3),
            [1, 2],
        )

        incomplete = json.dumps({
            "facets": [{"facet_index": 1}, {"facet_index": 2}],
            "accepted_indices": [1],
            "facet_coverage": [
                {"facet_index": 1, "passage_indices": [1]},
            ],
            "coverage_complete": False,
            "conflicts": [],
        })
        self.assertEqual(Generator._parse_precision_indices(incomplete, 3), [])

        declared_conflict = json.dumps({
            "facets": [{"facet_index": 1}],
            "accepted_indices": [1, 2],
            "facet_coverage": [
                {"facet_index": 1, "passage_indices": [1, 2]},
            ],
            "coverage_complete": True,
            "conflicts": ["older and latest projections differ"],
        })
        self.assertEqual(
            Generator._parse_precision_indices(
                declared_conflict, 2, allow_declared_conflicts=True
            ),
            [1, 2],
        )

    def test_precision_selector_fails_closed_without_adding_recall_anchors(self):
        generator = Generator(GeneratorConfig(
            llm=LLMConfig(model_name="fake"),
            evidence_selection_enabled=True,
            evidence_selection_mode="precision_v3",
            evidence_selection_anchor_chunks=2,
            evidence_selection_fail_closed=True,
        ))
        generator._llm = SequencedFakeLLM(["not-json"])
        retrieved = [
            RetrieveResult("c1", "d1", "jira", "possibly relevant", 1.0),
        ]
        self.assertEqual(generator.select_evidence("question", retrieved), [])

    def test_semantic_precision_selector_still_fails_closed(self):
        generator = Generator(GeneratorConfig(
            llm=LLMConfig(model_name="fake"),
            evidence_selection_enabled=True,
            evidence_selection_mode="precision_v3",
            evidence_selection_max_chunks=6,
            evidence_selection_fail_closed=True,
        ))
        generator._llm = SequencedFakeLLM([json.dumps({
            "facets": [{"facet_index": 1}],
            "accepted_indices": [],
            "facet_coverage": [],
            "coverage_complete": False,
            "conflicts": [],
        })])
        retrieved = [
            RetrieveResult("c1", "d1", "fireflies", "top paraphrase", 2.0),
            RetrieveResult("c2", "d2", "fireflies", "weaker match", 1.0),
        ]
        selected = generator.select_evidence(
            "paraphrased question", retrieved, "semantic"
        )
        self.assertEqual(selected, [])

    def test_completeness_precision_selector_keeps_bounded_routed_set(self):
        generator = Generator(GeneratorConfig(
            llm=LLMConfig(model_name="fake"),
            evidence_selection_enabled=True,
            evidence_selection_mode="precision_v3",
            evidence_selection_max_chunks=3,
            evidence_selection_fail_closed=True,
        ))
        generator._llm = SequencedFakeLLM([json.dumps({
            "facets": [{"facet_index": 1}],
            "accepted_indices": [],
            "facet_coverage": [],
            "coverage_complete": False,
            "conflicts": [],
        })])
        retrieved = [
            RetrieveResult(f"c{i}", f"d{i}", "jira", f"report {i}", 4.0 - i)
            for i in range(1, 5)
        ]
        selected = generator.select_evidence(
            "which channel has most reports?", retrieved, "completeness"
        )
        self.assertEqual([item.doc_id for item in selected], ["d1", "d2", "d3"])

    def test_fact_verifier_revises_answer_and_falls_back_if_malformed(self):
        generator = Generator(GeneratorConfig(
            llm=LLMConfig(model_name="fake"),
            max_context_chunks=1,
            fact_verification_enabled=True,
        ))
        generator._llm = SequencedFakeLLM([
            "draft with a wrong number",
            '{"answer": "verified answer"}',
        ])
        retrieved = [RetrieveResult("c1", "d1", "github", "evidence", 1.0)]
        answer, _doc_ids = generator.generate_with_sources("question", retrieved)
        self.assertEqual(answer, "verified answer")

        generator._llm = SequencedFakeLLM(["safe draft", "not json"])
        answer, _doc_ids = generator.generate_with_sources("question", retrieved)
        self.assertEqual(answer, "safe draft")

    def test_final_answer_audit_prunes_unused_document_ids(self):
        generator = Generator(GeneratorConfig(
            llm=LLMConfig(model_name="fake"),
            max_context_chunks=2,
            final_answer_audit_enabled=True,
        ))
        generator._llm = SequencedFakeLLM([
            "draft with an unnecessary number",
            json.dumps({
                "answer": "minimal supported answer",
                "used_evidence_indices": [2],
            }),
        ])
        retrieved = [
            RetrieveResult("c1", "d1", "gmail", "proposal", 2.0),
            RetrieveResult("c2", "d2", "jira", "applied record", 1.0),
        ]
        answer, doc_ids = generator.generate_with_sources("what was applied?", retrieved)
        self.assertEqual(answer, "minimal supported answer")
        self.assertEqual(doc_ids, ["d2"])


class HybridRoutingTests(unittest.TestCase):
    def test_question_types_map_to_distinct_evidence_modes(self):
        planner = EvidencePlanner()
        self.assertEqual(
            planner.plan("question", "basic").mode,
            "single",
        )
        self.assertEqual(
            planner.plan("question", "intra_document_reasoning").mode,
            "single_multisection",
        )
        self.assertTrue(planner.plan("question", "completeness").exhaustive)
        self.assertTrue(planner.plan("question", "info_not_found").abstain)

    def test_single_document_mode_keeps_wide_candidates_and_can_search_again(self):
        plan = EvidencePlanner().plan("question", "intra_document_reasoning")
        self.assertEqual(plan.estimated_documents, 1)
        self.assertGreaterEqual(plan.candidate_documents, 8)
        self.assertEqual(plan.max_hops, 2)

    def test_balanced_modes_widen_only_recall_sensitive_routes(self):
        planner = EvidencePlanner()
        semantic = planner.plan("question", "semantic")
        self.assertTrue(semantic.use_pageindex)
        self.assertEqual(semantic.max_hops, 1)
        self.assertGreaterEqual(
            planner.plan("question", "constrained").candidate_documents, 16
        )
        self.assertGreaterEqual(
            planner.plan("question", "completeness").candidate_documents, 24
        )
        self.assertEqual(planner.plan("question", "basic").candidate_documents, 10)

    def test_mode_guidance_distinguishes_latest_from_formal_approval(self):
        guidance = PageIndexHybridRouter._mode_guidance("conflict_pair")
        self.assertIn("latest available projection", guidance)
        self.assertIn("approved/applied", guidance)
        self.assertIn("preceding conflicting record", guidance)

    def test_exhaustive_guidance_counts_intake_events_not_topic_mentions(self):
        guidance = PageIndexHybridRouter._mode_guidance("exhaustive")
        self.assertIn("distinct intake artifact", guidance)
        self.assertIn("background specifications", guidance)

    def test_semantic_mode_has_wide_file_window_and_no_raw_es_fallback_intent(self):
        plan = EvidencePlanner().plan("question", "semantic")
        self.assertGreaterEqual(plan.candidate_documents, 30)
        self.assertGreaterEqual(plan.max_selected_nodes, 16)

    def test_semantic_call_prefers_direct_transcript_source(self):
        plan = EvidencePlanner().plan("question", "semantic")
        documents = [
            {"source_type": "google_drive", "doc_id": "notes"},
            {"source_type": "fireflies", "doc_id": "transcript"},
        ]
        selected = PageIndexHybridRouter._prefer_direct_semantic_event_source(
            "What were they told on the intro call?", plan, documents
        )
        self.assertEqual([item["doc_id"] for item in selected], ["transcript"])

    def test_facet_results_are_interleaved_before_file_selection(self):
        def result(chunk: str, doc: str) -> RetrieveResult:
            return RetrieveResult(chunk, doc, "jira", chunk, 1.0)

        merged = PageIndexHybridRouter._interleave_results(
            [result("base-1", "d1"), result("base-2", "d2")],
            [result("facet-1", "d3"), result("facet-2", "d4")],
        )
        self.assertEqual(
            [item.chunk_id for item in merged],
            ["base-1", "facet-1", "base-2", "facet-2"],
        )

    def test_second_hop_adds_entity_independent_slo_query(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            router = PageIndexHybridRouter(
                PageIndexRouterConfig(cache_dir=temp, max_followup_queries=3),
                LLMConfig(model_name="fake"),
            )
            router._llm = SequencedFakeLLM([
                '{"search_queries": ["Proxima SLO verification"]}',
            ])
            search_plan = QuestionSearchPlan(
                facets=("cause", "policy", "enterprise route SLO verification"),
                hard_constraints=("enterprise",),
                risk_dimensions=("quota-vs-overload",),
                search_queries=(),
            )
            selection = NodeSelection(
                selected=[], facet_coverage={}, missing_facets=[3],
                follow_up_queries=[], conflicts=[],
            )
            queries = router._build_missing_facet_queries(
                "question", search_plan, selection
            )
            self.assertIn("Hosted API SLO", queries[0])

    def test_final_state_authority_rejects_proposal_but_keeps_governing_spec(self):
        jira = RetrieveResult(
            "j1", "jira-final", "jira",
            "Approved a guarded exception. Applied policy override and recorded change in audit log.",
            1.0,
        )
        email = RetrieveResult(
            "e1", "email-proposal", "gmail",
            "Request temporary exception. Proposed burst ceiling; will implement if you confirm.",
            1.0,
        )
        spec = RetrieveResult(
            "s1", "slo-spec", "confluence",
            "Enterprise SLO policy and error budget specification.",
            1.0,
        )
        selection = NodeSelection(
            selected=[email, jira, spec],
            facet_coverage={1: ["e1", "j1"], 2: ["s1"]},
            missing_facets=[], follow_up_queries=[], conflicts=[],
        )
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            router = PageIndexHybridRouter(
                PageIndexRouterConfig(cache_dir=temp),
                LLMConfig(model_name="fake"),
            )
            filtered = router._authority_filter(
                "What temporary policy exception was applied?", selection
            )
        self.assertEqual(
            [item.doc_id for item in filtered.selected],
            ["jira-final", "slo-spec"],
        )
        self.assertIn("authority_rejected:email-proposal", filtered.conflicts)

    def test_authority_uses_full_file_when_selected_node_omits_finality(self):
        jira = RetrieveResult("j1", "jira-final", "jira", "Resolution", 1.0)
        email = RetrieveResult(
            "e1", "email-proposal", "gmail", "Temporary exception", 1.0
        )
        selection = NodeSelection(
            selected=[email, jira], facet_coverage={1: ["e1", "j1"]},
            missing_facets=[], follow_up_queries=[], conflicts=[],
        )

        class FullFileStore:
            @staticmethod
            def read(doc_id, source_type=None):
                if doc_id == "jira-final":
                    return (
                        "Approved a guarded exception. Applied policy override; "
                        "recorded change in audit log and marked resolved.",
                        "jira.txt",
                    )
                return (
                    "Request temporary exception. Proposed ceiling; "
                    "will implement after confirmation.",
                    "email.txt",
                )

        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            router = PageIndexHybridRouter(
                PageIndexRouterConfig(cache_dir=temp),
                LLMConfig(model_name="fake"),
            )
            router.store = FullFileStore()
            filtered = router._authority_filter(
                "What temporary policy exception was applied?", selection
            )
        self.assertEqual([item.doc_id for item in filtered.selected], ["jira-final"])
        self.assertIn("authority_rejected:email-proposal", filtered.conflicts)

    def test_partial_read_depth_expands_only_admitted_short_files(self):
        admitted = RetrieveResult("n1", "final-doc", "jira", "Final node", 1.0)

        class FullFileStore:
            @staticmethod
            def read(doc_id, source_type=None):
                return ("Root cause\nApplied exception\nSLO verification", "jira.txt")

        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            router = PageIndexHybridRouter(
                PageIndexRouterConfig(
                    cache_dir=temp, max_partial_full_document_chars=100
                ),
                LLMConfig(model_name="fake"),
            )
            router.store = FullFileStore()
            expanded = router._partial_full_document_results([admitted])
        self.assertEqual(len(expanded), 1)
        self.assertEqual(expanded[0].doc_id, "final-doc")
        self.assertTrue(expanded[0].chunk_id.endswith("__pageindex__full"))

    def test_final_audit_prompt_separates_incident_from_follow_up_state(self):
        self.assertIn("post-change reason mix", FINAL_ANSWER_AUDIT_USER_TEMPLATE)
        self.assertIn("availability/error-budget burn", FINAL_ANSWER_AUDIT_USER_TEMPLATE)

    def test_precision_gate_removes_unasked_post_change_clause_only(self):
        answer = (
            "Overload admission control was the cause. Verification used SLO burn; "
            "post-change 429 rate fell to 0.8% and the reason mix shifted to quota_exceeded."
        )
        cleaned = Generator._remove_unasked_follow_up_state(
            "What caused the incident and how was the SLO verified?", answer
        )
        self.assertEqual(
            cleaned, "Overload admission control was the cause. Verification used SLO burn."
        )
        self.assertEqual(
            Generator._remove_unasked_follow_up_state(
                "What was the post-change reason mix?", answer
            ),
            answer,
        )

    def test_precision_gate_repairs_only_evidence_supported_slots(self):
        question = "What caused it and how do we verify the enterprise route SLO?"
        evidence = RetrieveResult(
            "c1", "d1", "jira",
            "overload admission_over_budget, not quota; Retry-After 1-2. "
            "per route x region x tier SLO dashboard availability error budget "
            "p95 p99 5xx overload 429 shed_rate sustained alert",
            1.0,
        )
        repaired = Generator._repair_supported_coverage(
            question, [evidence], "Overload admission control caused it."
        )
        self.assertIn("not primarily a quota-limit issue", repaired)
        self.assertIn("1-2 second Retry-After", repaired)
        self.assertIn("route x region x tier", repaired)
        self.assertIn("availability/error-budget", repaired)
        self.assertIn("5xx", repaired)
        self.assertIn("shed_rate", repaired)

    def test_txt_adapter_builds_markdown_hierarchy(self):
        markdown = TextStructureAdapter.to_markdown(
            "Document title\n\nBackground:\nAlpha\n\nTimeline:\n- event",
            "jira",
        )
        self.assertIn("# Document title", markdown)
        self.assertIn("## Background", markdown)
        self.assertIn("## Timeline", markdown)
        words, headings = TextStructureAdapter.stats(markdown)
        self.assertGreater(words, 4)
        self.assertEqual(headings, 2)

    def test_txt_adapter_segments_unstructured_conversation(self):
        markdown = TextStructureAdapter.to_markdown(
            "Meeting transcript\n\nSpeaker A hello\n\nSpeaker B response",
            "fireflies",
        )
        self.assertIn("## Section 1", markdown)


class PageIndexV5FixesTests(unittest.TestCase):
    """Regression tests for the P1/P2 fixes in the v5 targeted run.

    Each test pins one deterministic behaviour; the real 5-question run still
    requires the server-side Elasticsearch index and Qwen endpoint.
    """

    def test_authority_filter_drops_proposal_email_without_policy_words(self):
        """P1-2: a proposal that never uses policy keywords must still lose to
        an applied ticket instead of passing the old "not policy" exemption."""
        jira = RetrieveResult(
            "j1", "jira-final", "jira",
            "Approved a guarded exception. Applied policy override and "
            "recorded change in audit log.",
            1.0,
        )
        email = RetrieveResult(
            "e1", "email-proposal", "gmail",
            "Proposed a new ceiling; we are waiting for confirmation.",
            1.0,
        )
        spec = RetrieveResult(
            "s1", "slo-spec", "confluence",
            "Enterprise SLO policy and error budget specification.",
            1.0,
        )
        selection = NodeSelection(
            selected=[email, jira, spec],
            facet_coverage={1: ["e1", "j1"], 2: ["s1"]},
            missing_facets=[], follow_up_queries=[], conflicts=[],
        )
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            router = PageIndexHybridRouter(
                PageIndexRouterConfig(cache_dir=temp),
                LLMConfig(model_name="fake"),
            )
            filtered = router._authority_filter(
                "What temporary policy exception was applied?", selection
            )
        self.assertEqual(
            [item.doc_id for item in filtered.selected],
            ["jira-final", "slo-spec"],
        )
        self.assertIn("authority_rejected:email-proposal", filtered.conflicts)

    def test_authority_filter_keeps_all_when_no_clear_authority(self):
        """P1-2: without a clearly authoritative record the filter is inert."""
        email = RetrieveResult(
            "e1", "email-discussion", "gmail",
            "We discussed the proposed timeline in the thread.",
            1.0,
        )
        notes = RetrieveResult(
            "d1", "drive-notes", "google_drive",
            "Meeting notes about the proposed approach.",
            1.0,
        )
        selection = NodeSelection(
            selected=[email, notes],
            facet_coverage={1: ["e1", "d1"]},
            missing_facets=[], follow_up_queries=[], conflicts=[],
        )
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            router = PageIndexHybridRouter(
                PageIndexRouterConfig(cache_dir=temp),
                LLMConfig(model_name="fake"),
            )
            filtered = router._authority_filter(
                "What was the current status?", selection
            )
        self.assertEqual(len(filtered.selected), 2)

    def test_exhaustive_filter_rejects_outbound_notice_by_content(self):
        """P1-3: content-level detection catches artifacts whose paths carry
        no outbound/follow-up marker."""
        class FullFileStore:
            @staticmethod
            def read(doc_id, source_type=None):
                if doc_id == "notice-doc":
                    return (
                        "Dear customer, we are writing to inform you that your "
                        "service tier will change.",
                        "gmail/plain.txt",
                    )
                return (
                    "Incident report: customer reported JSON schema timeouts.",
                    "jira/plain.txt",
                )

        plan = EvidencePlanner().plan("question", "completeness")
        documents = [
            {"doc_id": "notice-doc", "source_type": "gmail",
             "source_path": "gmail/plain.txt", "nodes": []},
            {"doc_id": "report-doc", "source_type": "jira",
             "source_path": "jira/plain.txt", "nodes": []},
        ]
        selection = NodeSelection(
            selected=[
                RetrieveResult("n1", "notice-doc", "gmail", "notice", 1.0),
                RetrieveResult("r1", "report-doc", "jira", "report", 1.0),
            ],
            facet_coverage={1: ["n1", "r1"]},
            missing_facets=[], follow_up_queries=[], conflicts=[],
        )
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            router = PageIndexHybridRouter(
                PageIndexRouterConfig(cache_dir=temp),
                LLMConfig(model_name="fake"),
            )
            router.store = FullFileStore()
            filtered = router._filter_exhaustive_artifacts(
                "Which channel received the most reports about JSON schema timeouts?",
                plan, documents, selection,
            )
        self.assertEqual(
            [item.doc_id for item in filtered.selected], ["report-doc"]
        )
        self.assertIn(
            "non_intake_artifact_rejected:notice-doc", filtered.conflicts
        )

    def test_semantic_partial_selection_reads_full_direct_event(self):
        """P1-1: a partially covered semantic route reads the complete direct
        event artifact (Fireflies transcript beyond the generic 18k cap) once
        the event source has been narrowed."""
        full_transcript = "T" * 20000

        class FullFileStore:
            @staticmethod
            def read(doc_id, source_type=None):
                return (full_transcript, "fireflies/transcript.txt")

        def retrieve_query(_query):
            return []

        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            markdown = TextStructureAdapter.to_markdown(
                full_transcript, "fireflies"
            )
            fingerprint = hashlib.sha256(
                (PAGEINDEX_ADAPTER_VERSION + "\0" + markdown).encode("utf-8")
            ).hexdigest()
            tree = {
                "doc_id": "ff-doc",
                "source_type": "fireflies",
                "source_path": "fireflies/transcript.txt",
                "fingerprint": fingerprint,
                "adapter_version": PAGEINDEX_ADAPTER_VERSION,
                "word_count": 1000,
                "heading_count": 5,
                "structure": [{
                    "node_id": "0001", "title": "Section 1",
                    "text": "call transcript content", "nodes": [],
                }],
            }
            cache = Path(temp) / f"ff-doc-{fingerprint[:16]}.json"
            cache.write_text(json.dumps(tree), encoding="utf-8")

            router = PageIndexHybridRouter(
                PageIndexRouterConfig(cache_dir=temp, max_hops=1, enabled=True),
                LLMConfig(model_name="fake"),
            )
            router.store = FullFileStore()
            router._llm = SequencedFakeLLM([
                json.dumps({
                    "facets": ["timeline"],
                    "hard_constraints": ["entity: partner"],
                    "risk_dimensions": [],
                    "search_queries": [],
                }),
                json.dumps({
                    "selected": [{
                        "file": 1, "node_ids": ["0001"],
                        "facet_indices": [1], "admit": True,
                        "evidence_status": "current", "reason": "direct",
                    }],
                    "missing_facet_indices": [1],
                    "follow_up_queries": [], "conflicts": [],
                }),
                json.dumps({
                    "accepted_indices": [1],
                    "facet_coverage": [
                        {"facet_index": 1, "evidence_indices": [1]}
                    ],
                    "rejected": [], "unresolved_facet_indices": [1],
                }),
            ])
            routed = router.route(
                "What timeline was discussed on the intro call with the partner?",
                "semantic",
                [RetrieveResult("c1", "ff-doc", "fireflies", "chunk", 1.0)],
                retrieve_callback=retrieve_query,
            )
        self.assertTrue(
            any(item.chunk_id.endswith("__pageindex__event_full")
                for item in routed),
            "expected the full direct event artifact in the routed evidence",
        )
        self.assertEqual(
            router.last_trace["route_action"], "pageindex_partial_full_scoped"
        )

    def test_conflict_version_pair_queries_use_entity(self):
        """P2-2: version-pair second hop searches carry the entity name."""
        search_plan = QuestionSearchPlan(
            facets=("qps", "concurrency"),
            hard_constraints=("entity: ClearEdge", "region: us-east"),
            risk_dimensions=("version/finality",),
            search_queries=(),
        )
        queries = PageIndexHybridRouter._build_version_pair_queries(search_plan)
        self.assertTrue(any("clearedge" in query.casefold() for query in queries))
        self.assertTrue(any("previous version" in query for query in queries))

    def test_version_pair_queries_empty_without_entity(self):
        search_plan = QuestionSearchPlan(
            facets=("qps",), hard_constraints=("region: us-east",),
            risk_dimensions=(), search_queries=(),
        )
        self.assertEqual(
            PageIndexHybridRouter._build_version_pair_queries(search_plan), []
        )

    def test_missing_facet_queries_add_org_search(self):
        """P2-1: high-level synthesis gets an org-chart authoritative search."""
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            router = PageIndexHybridRouter(
                PageIndexRouterConfig(cache_dir=temp),
                LLMConfig(model_name="fake"),
            )
            router._llm = SequencedFakeLLM(['{"search_queries": []}'])
            search_plan = QuestionSearchPlan(
                facets=("top-level departments",),
                hard_constraints=(), risk_dimensions=(), search_queries=(),
            )
            selection = NodeSelection(
                [], {}, [1], [], []
            )
            queries = router._build_missing_facet_queries(
                "Which departments exist?", search_plan, selection
            )
        self.assertTrue(any("organization chart" in query for query in queries))

    def test_glyph_normalization_is_deterministic_and_safe(self):
        """6.6: erroneous glyphs are normalized without touching text semantics."""
        self.assertEqual(
            Generator._normalize_typo_glyphs("2每4 weeks, ≧10%"),
            "2-4 weeks, >=10%",
        )
        self.assertEqual(
            Generator._normalize_typo_glyphs("每周 review at 3每5"),
            "每周 review at 3-5",
        )
        self.assertEqual(
            Generator._normalize_typo_glyphs("x ≦ y × z"),
            "x <= y x z",
        )

    def test_glyph_normalization_fixes_corrupted_en_dash(self):
        """6.6 follow-up: corrupted en-dash bytes surface as digit + U+FFFD."""
        self.assertEqual(
            Generator._normalize_typo_glyphs("2�C4 weeks"),
            "2-4 weeks",
        )
        self.assertEqual(
            Generator._normalize_typo_glyphs("10�C30s spikes, 6�C12% bursts"),
            "10-30s spikes, 6-12% bursts",
        )
        self.assertEqual(
            Generator._normalize_typo_glyphs("orphan � char removed"),
            "orphan  char removed",
        )

    def test_multi_hop_partial_reexposes_authority_files(self):
        """qst_0341: files that passed the authority filter but whose nodes
        were all rejected by the auditor return as bounded full documents."""
        jira = RetrieveResult(
            "j1", "jira-doc", "jira", "Hypothesis section", 1.0
        )
        slo = RetrieveResult(
            "s1", "slo-doc", "confluence", "SLO verification", 1.0
        )

        class FullFileStore:
            @staticmethod
            def read(doc_id, source_type=None):
                if doc_id == "jira-doc":
                    return (
                        "Applied policy override and recorded change in audit log.",
                        "jira.txt",
                    )
                return ("Enterprise SLO policy and error budget.", "slo.txt")

        def write_tree(temp: str, doc_id: str, source_type: str, text: str,
                       node_id: str):
            markdown = TextStructureAdapter.to_markdown(text, source_type)
            fingerprint = hashlib.sha256(
                (PAGEINDEX_ADAPTER_VERSION + "\0" + markdown).encode("utf-8")
            ).hexdigest()
            tree = {
                "doc_id": doc_id, "source_type": source_type,
                "source_path": f"{doc_id}.txt", "fingerprint": fingerprint,
                "adapter_version": PAGEINDEX_ADAPTER_VERSION,
                "word_count": 500, "heading_count": 5,
                "structure": [{
                    "node_id": node_id, "title": "Section",
                    "text": text, "nodes": [],
                }],
            }
            cache = Path(temp) / f"{doc_id}-{fingerprint[:16]}.json"
            cache.write_text(json.dumps(tree), encoding="utf-8")

        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            write_tree(temp, "jira-doc", "jira",
                       "Applied policy override and recorded change in audit log.",
                       "0001")
            write_tree(temp, "slo-doc", "confluence",
                       "Enterprise SLO policy and error budget.", "0002")
            router = PageIndexHybridRouter(
                PageIndexRouterConfig(cache_dir=temp, enabled=True, max_hops=1),
                LLMConfig(model_name="fake"),
            )
            router.store = FullFileStore()
            router._llm = SequencedFakeLLM([
                json.dumps({
                    "facets": ["cause", "exception", "verification"],
                    "hard_constraints": ["Entity: Bank", "Event: 429 spike"],
                    "risk_dimensions": [], "search_queries": [],
                }),
                json.dumps({
                    "selected": [
                        {"file": 1, "node_ids": ["0001"], "facet_indices": [1],
                         "admit": True, "evidence_status": "current",
                         "reason": "direct"},
                        {"file": 2, "node_ids": ["0002"], "facet_indices": [3],
                         "admit": True, "evidence_status": "current",
                         "reason": "verification"},
                    ],
                    "missing_facet_indices": [1, 2],
                    "follow_up_queries": [], "conflicts": [],
                }),
                json.dumps({
                    "accepted_indices": [2],
                    "facet_coverage": [
                        {"facet_index": 3, "evidence_indices": [2]}
                    ],
                    "rejected": [], "unresolved_facet_indices": [1, 2],
                }),
            ])
            routed = router.route(
                "What temporary exception was applied?",
                "project_related",
                [
                    RetrieveResult("c1", "jira-doc", "jira", "chunk", 1.0),
                    RetrieveResult("c2", "slo-doc", "confluence", "chunk", 0.9),
                ],
                retrieve_callback=lambda _query: [],
            )
        self.assertTrue(
            any(item.chunk_id.endswith("__pageindex__authority_full")
                for item in routed),
            "jira file must re-enter as a bounded full document",
        )
        self.assertEqual(
            router.last_trace["route_action"], "pageindex_partial_full_scoped"
        )

    def test_high_level_generator_bypasses_fail_closed_selector(self):
        """qst_0480: high_level synthesis keeps the scoped candidate set even
        when the precision selector would return an empty accepted set."""
        generator = Generator(GeneratorConfig(
            llm=LLMConfig(model_name="fake"),
            evidence_selection_enabled=True,
            evidence_selection_mode="precision_v3",
            evidence_selection_candidate_chunks=3,
            evidence_selection_max_chunks=3,
            evidence_selection_fail_closed=True,
        ))
        generator._llm = SequencedFakeLLM([json.dumps({
            "facets": [{"facet_index": 1}],
            "accepted_indices": [],
            "facet_coverage": [],
            "coverage_complete": False,
            "conflicts": [],
        })])
        retrieved = [
            RetrieveResult(f"c{i}", f"d{i}", "confluence", f"org clue {i}", 3.0 - i)
            for i in range(1, 4)
        ]
        selected = generator.select_evidence(
            "What are the major departments?", retrieved, "high_level"
        )
        self.assertEqual(
            [item.doc_id for item in selected], ["d1", "d2", "d3"]
        )


class LLMClientTests(unittest.TestCase):
    def test_extra_body_is_sent_and_reasoning_is_not_leaked_in_errors(self):
        config = LLMConfig(
            api_base="http://example.test/v1",
            api_key_env="TEST_LLM_KEY",
            model_name="model",
            retry_attempts=1,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        client = OpenAICompatibleClient(config)
        response = FakeHTTPResponse({
            "choices": [{
                "finish_reason": "length",
                "message": {"content": None, "reasoning": "private reasoning"},
            }]
        })
        with mock.patch.dict(os.environ, {"TEST_LLM_KEY": "test"}), mock.patch(
            "urllib.request.urlopen", return_value=response
        ) as urlopen:
            answer = client.generate("prompt")
        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertFalse(payload["chat_template_kwargs"]["enable_thinking"])
        self.assertTrue(answer.startswith("[LLM_ERROR:"))
        self.assertNotIn("private reasoning", answer)


class IndexerReliabilityTests(unittest.TestCase):
    def test_duplicate_doc_ids_get_path_disambiguated_chunk_ids(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            root = Path(temp)
            for source, text in (("jira", "alpha"), ("hubspot", "beta")):
                directory = root / "corpus" / source
                directory.mkdir(parents=True)
                (directory / "dsid_shared__record.txt").write_text(
                    text, encoding="utf-8"
                )
            indexer = Indexer(IndexerConfig(
                corpus_dir=str(root / "corpus"),
                cache_dir=str(root / "cache"),
                enable_faiss=False,
                enable_bm25=False,
            ))
            meta = indexer.build()
            self.assertEqual(len(indexer.chunks), 2)
            self.assertEqual(len({chunk.chunk_id for chunk in indexer.chunks}), 2)
            self.assertEqual({chunk.doc_id for chunk in indexer.chunks}, {"dsid_shared"})
            self.assertTrue(all("__dup-" in chunk.chunk_id for chunk in indexer.chunks))
            self.assertEqual(meta["duplicate_doc_ids"], 1)

    def test_manifest_cache_and_fingerprint_refresh(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            root = Path(temp)
            corpus = root / "corpus" / "github"
            corpus.mkdir(parents=True)
            (corpus / "dsid_one__one.txt").write_text(
                "alpha beta gamma", encoding="utf-8"
            )
            cache = root / "cache"
            config = IndexerConfig(
                corpus_dir=str(root / "corpus"),
                cache_dir=str(cache),
                chunk_size=2,
                enable_faiss=False,
            )
            first = Indexer(config)
            meta = first.build()
            self.assertEqual(meta["num_docs"], 1)
            self.assertTrue((cache / "manifest.sqlite3").exists())
            self.assertTrue(all("fixed-v2" in c.chunk_id for c in first.chunks))

            cached = Indexer(config)
            cached_meta = cached.build()
            self.assertEqual(cached_meta["index_fingerprint"], meta["index_fingerprint"])

            (corpus / "dsid_two__two.txt").write_text("delta", encoding="utf-8")
            refreshed = Indexer(config)
            refreshed_meta = refreshed.build()
            self.assertEqual(refreshed_meta["num_docs"], 2)


if __name__ == "__main__":
    unittest.main()
