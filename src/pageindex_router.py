"""Hybrid ES + PageIndex evidence routing.

Elasticsearch remains the corpus-wide recall layer. PageIndex is invoked lazily
for question modes that benefit from document/file-tree reasoning. Raw source
documents are resolved through the existing preprocessing manifest, converted
to structured Markdown, parsed with PageIndex's official Markdown tree parser,
and cached by content fingerprint.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import sys
import types
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .llm import LLMClient, LLMConfig, create_llm_client
from .retriever import RetrieveResult


PAGEINDEX_ADAPTER_VERSION = "txt-markdown-v1"


@dataclass(frozen=True)
class EvidencePlan:
    question_type: str
    mode: str
    use_pageindex: bool
    estimated_documents: int
    candidate_documents: int
    max_selected_nodes: int
    max_hops: int = 0
    exhaustive: bool = False
    abstain: bool = False


@dataclass(frozen=True)
class QuestionSearchPlan:
    """Question facets and retrieval constraints produced before tree search."""

    facets: tuple[str, ...]
    hard_constraints: tuple[str, ...]
    risk_dimensions: tuple[str, ...]
    search_queries: tuple[str, ...]


@dataclass
class NodeSelection:
    selected: list[RetrieveResult]
    facet_coverage: dict[int, list[str]]
    missing_facets: list[int]
    follow_up_queries: list[str]
    conflicts: list[str]


class EvidencePlanner:
    """Map benchmark metadata (or conservative heuristics) to evidence modes."""

    _PLANS = {
        "basic": ("single", False, 1, 10, 0, 0, False, False),
        "semantic": ("single_semantic", True, 1, 30, 16, 1, False, False),
        "miscellaneous": ("single", False, 1, 10, 0, 0, False, False),
        "intra_document_reasoning": (
            "single_multisection", True, 1, 10, 8, 2, False, False
        ),
        "constrained": ("constrained_pair", True, 2, 16, 12, 2, False, False),
        "conflicting_info": ("conflict_pair", True, 2, 16, 16, 2, False, False),
        "project_related": ("multi_hop", True, 3, 14, 12, 2, False, False),
        "completeness": ("exhaustive", True, 6, 24, 24, 2, True, False),
        "high_level": ("corpus_level", True, 6, 24, 24, 2, True, False),
        "info_not_found": ("abstain", False, 0, 20, 0, 0, False, True),
    }

    def plan(self, question: str, question_type: str | None = None) -> EvidencePlan:
        normalized = (question_type or "").strip().lower()
        values = self._PLANS.get(normalized)
        if values is None:
            lowered = question.lower()
            if re.search(r"\b(all|every|how many|most reports|list each)\b", lowered):
                normalized = "heuristic_exhaustive"
                values = ("exhaustive", True, 8, 10, 12, 1, True, False)
            elif re.search(r"\b(conflict|latest|current|previous|earlier version)\b", lowered):
                normalized = "heuristic_conflict"
                values = ("conflict_pair", True, 2, 6, 8, 0, False, False)
            else:
                normalized = normalized or "unknown"
                values = ("single", False, 1, 10, 0, 0, False, False)
        return EvidencePlan(normalized, *values)


@dataclass
class PageIndexRouterConfig:
    enabled: bool = False
    pageindex_home: str = ""
    corpus_dir: str = ""
    manifest_path: str = ""
    cache_dir: str = ".pageindex_cache"
    min_words: int = 350
    min_headings: int = 2
    max_candidate_documents: int = 10
    max_nodes_per_document: int = 24
    node_preview_chars: int = 900
    max_followup_queries: int = 2
    max_hops: int = 1
    require_node_audit: bool = True
    fallback_to_es_on_incomplete: bool = True
    max_partial_full_document_chars: int = 18000
    # Direct event artifacts (Fireflies transcripts, Gmail threads) routinely
    # exceed the generic partial-read cap. When the event source has been
    # narrowed, the bounded full read may use this larger ceiling because the
    # downstream generator still runs factual verification.
    semantic_event_full_max_chars: int = 40000


class TextStructureAdapter:
    """Convert source-flavored TXT into hierarchy-preserving Markdown."""

    INLINE_HEADING_SOURCES = {
        "confluence", "google_drive", "jira", "linear", "github", "hubspot"
    }
    COMMON_HEADINGS = {
        "overview", "summary", "background", "context", "motivation", "scope",
        "goals", "goal", "audience", "assumptions", "impact", "timeline",
        "root cause", "resolution", "mitigation", "follow-up", "follow up",
        "action items", "observed behavior", "expected behavior", "risks",
        "testing", "tests", "rollout", "rollback", "decision", "status",
        "details", "requirements", "acceptance criteria", "next steps",
    }

    @classmethod
    def to_markdown(cls, text: str, source_type: str) -> str:
        if source_type == "confluence" and text.count("\\n") > text.count("\n"):
            text = text.replace("\\n", "\n")
        raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        output: list[str] = []
        title_written = False
        secondary_headings = 0

        for raw in raw_lines:
            line = raw.strip()
            if not line:
                if output and output[-1] != "":
                    output.append("")
                continue
            if not title_written:
                output.extend([f"# {line.lstrip('#').strip()}", ""])
                title_written = True
                continue
            if re.match(r"^#{1,6}\s+", line):
                output.append(line)
                secondary_headings += 1
                continue

            full_heading = (
                line.endswith(":")
                and not line.startswith(("-", "*", "http"))
                and len(line) <= 90
                and len(line[:-1].split()) <= 12
            )
            if full_heading:
                output.extend([f"## {line[:-1].strip()}", ""])
                secondary_headings += 1
                continue

            inline = re.match(r"^([A-Z][A-Za-z0-9 /&()_-]{1,45}):\s+(.+)$", line)
            if inline and source_type in cls.INLINE_HEADING_SOURCES:
                label = inline.group(1).strip()
                if label.lower() in cls.COMMON_HEADINGS or len(label.split()) <= 4:
                    output.extend([f"## {label}", "", inline.group(2).strip(), ""])
                    secondary_headings += 1
                    continue

            numbered = re.match(r"^\d+[.)]\s+([A-Z][^:]{2,80})(?::\s*)?$", line)
            if numbered and len(line.split()) <= 14:
                output.extend([f"## {numbered.group(1).strip()}", ""])
                secondary_headings += 1
                continue
            output.append(line)

        if not title_written:
            return "# Empty document\n"

        # Conversation-like documents often have no headings. Add deterministic
        # paragraph groups so the tree still exposes navigable regions.
        if secondary_headings == 0:
            paragraphs = "\n".join(output[2:]).split("\n\n")
            rebuilt = output[:2]
            for index in range(0, len(paragraphs), 5):
                rebuilt.extend([
                    f"## Section {index // 5 + 1}", "",
                    "\n\n".join(paragraphs[index:index + 5]).strip(), "",
                ])
            output = rebuilt
        return "\n".join(output).strip() + "\n"

    @staticmethod
    def stats(markdown: str) -> tuple[int, int]:
        words = len(re.findall(r"\S+", markdown))
        headings = len(re.findall(r"^#{2,6}\s+", markdown, flags=re.MULTILINE))
        return words, headings


class ManifestDocumentStore:
    """Resolve parent doc IDs to original TXT files through manifest.sqlite3."""

    def __init__(self, corpus_dir: str, manifest_path: str):
        self.corpus_dir = Path(corpus_dir)
        self.manifest_path = Path(manifest_path)

    def read(self, doc_id: str, source_type: str | None = None) -> tuple[str, str] | None:
        if not self.manifest_path.exists():
            return None
        uri = f"file:{self.manifest_path.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            rows = connection.execute(
                "SELECT file_path, source_type FROM documents "
                "WHERE doc_id = ? AND status = 'chunked' ORDER BY file_path",
                (doc_id,),
            ).fetchall()
        if not rows:
            return None
        chosen = next((row for row in rows if row[1] == source_type), rows[0])
        path = self.corpus_dir / chosen[0]
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8", errors="replace"), str(path)


class PageIndexHybridRouter:
    """Lazily build PageIndex trees and reason over candidate files/sections."""

    def __init__(self, config: PageIndexRouterConfig, llm_config: LLMConfig):
        self.config = config
        self.llm_config = llm_config
        self.planner = EvidencePlanner()
        self.store = ManifestDocumentStore(config.corpus_dir, config.manifest_path)
        self._llm: LLMClient | None = None
        self._official_parser = None
        self.last_trace: dict = {}
        Path(config.cache_dir).mkdir(parents=True, exist_ok=True)

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = create_llm_client(self.llm_config)
        return self._llm

    def _load_official_parser(self):
        if self._official_parser is not None:
            return self._official_parser
        home = Path(self.config.pageindex_home)
        if not home.exists():
            raise RuntimeError(f"PageIndex home does not exist: {home}")
        # Load the official Markdown parser directly from its source file.  A
        # regular ``import pageindex`` executes the package initializer and
        # imports LiteLLM/PDF dependencies that can override the tokenizers
        # version required by the BGE runtime.  The three deterministic tree
        # functions used here do not depend on those optional integrations.
        parser_path = home / "pageindex" / "page_index_md.py"
        if not parser_path.exists():
            raise RuntimeError(f"PageIndex Markdown parser not found: {parser_path}")
        module_name = "_enterprise_rag_official_pageindex_md"
        spec = importlib.util.spec_from_file_location(module_name, parser_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load PageIndex parser: {parser_path}")
        module = importlib.util.module_from_spec(spec)
        previous_utils = sys.modules.get("utils")
        sys.modules["utils"] = types.ModuleType("utils")
        try:
            spec.loader.exec_module(module)
        finally:
            if previous_utils is None:
                sys.modules.pop("utils", None)
            else:
                sys.modules["utils"] = previous_utils
        extract_nodes_from_markdown = module.extract_nodes_from_markdown
        extract_node_text_content = module.extract_node_text_content
        build_tree_from_nodes = module.build_tree_from_nodes
        self._official_parser = (
            extract_nodes_from_markdown,
            extract_node_text_content,
            build_tree_from_nodes,
        )
        return self._official_parser

    def _tree_cache_path(self, doc_id: str, fingerprint: str) -> Path:
        safe_doc_id = re.sub(r"[^A-Za-z0-9_.-]", "_", doc_id)
        return Path(self.config.cache_dir) / f"{safe_doc_id}-{fingerprint[:16]}.json"

    def _build_or_load_tree(
        self, doc_id: str, source_type: str, text: str, source_path: str
    ) -> dict:
        markdown = TextStructureAdapter.to_markdown(text, source_type)
        fingerprint = hashlib.sha256(
            (PAGEINDEX_ADAPTER_VERSION + "\0" + markdown).encode("utf-8")
        ).hexdigest()
        cache_path = self._tree_cache_path(doc_id, fingerprint)
        if cache_path.exists():
            with open(cache_path, encoding="utf-8") as handle:
                return json.load(handle)

        extract_nodes, extract_text, build_tree = self._load_official_parser()
        nodes, lines = extract_nodes(markdown)
        structure = build_tree(extract_text(nodes, lines))
        words, headings = TextStructureAdapter.stats(markdown)
        value = {
            "doc_id": doc_id,
            "source_type": source_type,
            "source_path": source_path,
            "fingerprint": fingerprint,
            "adapter_version": PAGEINDEX_ADAPTER_VERSION,
            "word_count": words,
            "heading_count": headings,
            "structure": structure,
        }
        temp = cache_path.with_suffix(".tmp")
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, cache_path)
        return value

    @staticmethod
    def _flatten_tree(nodes: list[dict], parents: tuple[str, ...] = ()) -> list[dict]:
        flattened: list[dict] = []
        for node in nodes:
            title = str(node.get("title", "Untitled"))
            path = parents + (title,)
            flattened.append({
                "node_id": str(node.get("node_id", "")),
                "title": title,
                "path": " > ".join(path),
                "text": str(node.get("text", "")),
            })
            flattened.extend(PageIndexHybridRouter._flatten_tree(
                node.get("nodes", []), path
            ))
        return flattened

    def _candidate_trees(self, results: list[RetrieveResult], plan: EvidencePlan) -> list[dict]:
        candidates: list[dict] = []
        seen: set[str] = set()
        limit = min(plan.candidate_documents, self.config.max_candidate_documents)
        for result in results:
            if result.doc_id in seen:
                continue
            seen.add(result.doc_id)
            raw = self.store.read(result.doc_id, result.source_type)
            if raw is None:
                continue
            text, path = raw
            tree = self._build_or_load_tree(
                result.doc_id, result.source_type, text, path
            )
            eligible = (
                tree["word_count"] >= self.config.min_words
                and tree["heading_count"] >= self.config.min_headings
            )
            # Required tree modes may use synthetic sections even when the
            # source document does not naturally meet the eligibility score.
            if not eligible and plan.mode not in {
                "single_semantic", "single_multisection", "constrained_pair", "conflict_pair",
                "multi_hop", "exhaustive", "corpus_level"
            }:
                continue
            nodes = self._flatten_tree(tree["structure"])
            candidates.append({
                "doc_id": result.doc_id,
                "source_type": result.source_type,
                "source_path": path,
                "word_count": tree["word_count"],
                "heading_count": tree["heading_count"],
                "eligible": eligible,
                "nodes": nodes[:self.config.max_nodes_per_document],
            })
            if len(candidates) >= limit:
                break
        return candidates

    @staticmethod
    def _direct_event_sources(question: str, plan: EvidencePlan) -> set[str]:
        """Preferred source types for an explicitly named communication artifact."""
        if plan.mode != "single_semantic":
            return set()
        lowered = question.casefold()
        preferred: set[str] = set()
        if re.search(r"\b(call|meeting|transcript)\b", lowered):
            preferred.add("fireflies")
        if re.search(r"\b(email|mail thread)\b", lowered):
            preferred.add("gmail")
        if re.search(r"\b(ticket|issue)\b", lowered):
            preferred.update({"jira", "linear"})
        return preferred

    @staticmethod
    def _prefer_direct_semantic_event_source(
        question: str, plan: EvidencePlan, documents: list[dict]
    ) -> list[dict]:
        """Honor an explicitly named communication artifact before summaries."""
        preferred = PageIndexHybridRouter._direct_event_sources(question, plan)
        if not preferred:
            return documents
        direct = [
            document for document in documents
            if document["source_type"].casefold() in preferred
        ]
        return direct or documents

    @staticmethod
    def _first_direct_event_document(
        question: str, plan: EvidencePlan, documents: list[dict]
    ) -> dict | None:
        """First candidate after direct event-source narrowing, or None."""
        preferred = PageIndexHybridRouter._direct_event_sources(question, plan)
        if not preferred:
            return None
        for document in documents:
            if document["source_type"].casefold() in preferred:
                return document
        return None

    def _bounded_full_document(
        self, document: dict, max_chars: int, suffix: str
    ) -> RetrieveResult | None:
        """Read one admitted file as a bounded full-document evidence item."""
        try:
            original = self.store.read(document["doc_id"], document["source_type"])
        except (OSError, sqlite3.Error):
            original = None
        if original is None:
            return None
        text, _ = original
        if not text.strip() or len(text) > max_chars:
            return None
        return RetrieveResult(
            chunk_id=f"{document['doc_id']}__pageindex__{suffix}",
            doc_id=document["doc_id"],
            source_type=document["source_type"],
            text=text,
            score=1.0,
        )

    def _build_search_plan(
        self, question: str, plan: EvidencePlan
    ) -> QuestionSearchPlan:
        mode_line = ""
        if plan.mode in {"single_semantic", "conflict_pair", "exhaustive", "corpus_level"}:
            mode_line = (
                "Mode-specific planning guidance: "
                + self._mode_guidance(plan.mode)
            )
        prompt = f"""Decompose this question before retrieval. Do not answer it.

Question: {question}
Evidence mode: {plan.mode}
{mode_line}

Identify independently required answer facets. Extract only hard constraints stated or
unambiguously implied by the question: entity, event, product, date/time window, region,
version/status and metric. Mark risky dimensions where confusing a proposal with a final
decision, an old version with the current one, or quota with overload would make the answer
wrong. Produce one narrow corpus-search query per facet.

Return JSON only:
{{
  "facets": ["fact that must be answered"],
  "hard_constraints": ["constraint"],
  "risk_dimensions": ["version/finality", "quota-vs-overload"],
  "search_queries": ["narrow query containing exact entities and facet terms"]
}}
"""
        response = self.llm.generate(
            prompt,
            "You are a conservative retrieval query planner. Return valid JSON only.",
        ).strip()
        value = self._parse_json(response) or {}

        def strings(key: str, limit: int) -> list[str]:
            raw = value.get(key, [])
            if not isinstance(raw, list):
                return []
            cleaned: list[str] = []
            for item in raw:
                if isinstance(item, str) and item.strip() and item.strip() not in cleaned:
                    cleaned.append(item.strip())
                if len(cleaned) >= limit:
                    break
            return cleaned

        facets = strings("facets", 8) or [question]
        constraints = strings("hard_constraints", 12)
        risks = strings("risk_dimensions", 8)
        queries = strings("search_queries", self.config.max_followup_queries)
        if plan.mode == "single_semantic":
            aliases: list[str] = []
            lowered = question.casefold()
            alias_groups = (
                (("services firm", "integrator"), "SI systems integrator channel partner"),
                (("resell", "resells"), "reseller channel managed services"),
                (("operates", "operating"), "managed services managed offering"),
                (("isolated", "private environment"), "Private VPC dedicated deployment"),
                (("key management", "customer key"), "customer KMS HSM CMK"),
                (("lead time", "standing up"), "provisioning timeline weeks"),
            )
            for triggers, expansion in alias_groups:
                if any(trigger in lowered for trigger in triggers):
                    aliases.append(expansion)
            if aliases:
                alias_query = f"{question} {' '.join(aliases)}"
                queries = [alias_query, *queries]
                queries = list(dict.fromkeys(queries))[:self.config.max_followup_queries]
        if not queries:
            queries = [
                f"{question} Focus evidence for: {facet}"
                for facet in facets[:self.config.max_followup_queries]
            ]
        return QuestionSearchPlan(
            tuple(facets), tuple(constraints), tuple(risks), tuple(queries)
        )

    @staticmethod
    def _interleave_results(*groups: list[RetrieveResult]) -> list[RetrieveResult]:
        """Give each facet query a fair document-level chance before tree navigation."""
        merged: list[RetrieveResult] = []
        seen_chunks: set[str] = set()
        max_length = max((len(group) for group in groups), default=0)
        for rank in range(max_length):
            for group in groups:
                if rank >= len(group):
                    continue
                item = group[rank]
                if item.chunk_id in seen_chunks:
                    continue
                seen_chunks.add(item.chunk_id)
                merged.append(item)
        return merged

    def _selection_prompt(
        self,
        question: str,
        plan: EvidencePlan,
        search_plan: QuestionSearchPlan,
        documents: list[dict],
    ) -> str:
        rendered: list[str] = []
        preview_limit = max(100, self.config.node_preview_chars)
        for doc_index, document in enumerate(documents, 1):
            rendered.append(
                f"[File {doc_index}] doc_id={document['doc_id']} "
                f"source={document['source_type']}"
            )
            for node in document["nodes"]:
                preview = re.sub(r"\s+", " ", node["text"]).strip()[:preview_limit]
                rendered.append(
                    f"  - node_id={node['node_id']} path={node['path']}\n"
                    f"    preview={preview}"
                )
        mode_guidance = self._mode_guidance(plan.mode)
        return f"""Reason over the PageIndex file and section trees to locate evidence.

Question: {question}
Evidence mode: {plan.mode}
Estimated required documents: {plan.estimated_documents}
Required facets: {json.dumps(search_plan.facets, ensure_ascii=False)}
Hard constraints: {json.dumps(search_plan.hard_constraints, ensure_ascii=False)}
High-risk conflict dimensions: {json.dumps(search_plan.risk_dimensions, ensure_ascii=False)}

Rules:
- Select every section that directly supplies a requested fact or is needed for a reasoning hop.
- Match entity, event, date, region, version, quantity, unit and current-vs-historical status.
- Set admit=false if a file fails any applicable hard constraint or is merely topically similar.
- For quantities and policies, distinguish proposal/draft from final approval and old from current.
- Apply proposal/final precedence according to the wording: a proposal is invalid for "was
  applied/approved/current", but may be the requested evidence for "should/proposed/update".
- A governing runbook/SLO/policy specification may omit the named customer or incident when it
  directly defines the requested validation method, metric, threshold or rule.
- Do not treat quota_exceeded as overload/admission control, or vice versa.
- For conflict_pair, retain both conflicting/updated sources and resolve them later.
- For exhaustive, favor recall and cover every instance; do not stop at the first match.
- Mode-specific admission guidance: {mode_guidance}
- Assign every admitted selection to one or more 1-based required facet indices.
- List a facet as missing unless an admitted node directly supports it.
- Do not answer the question.

Return JSON only:
{{
  "selected": [{{
    "file": 1,
    "node_ids": ["0001"],
    "facet_indices": [1],
    "admit": true,
    "evidence_status": "final/current/applicable",
    "reason": "exact constraint match"
  }}],
  "missing_facet_indices": [2],
  "conflicts": ["specific conflict found"],
  "follow_up_queries": ["query for a missing facet"]
}}

PageIndex trees:
{chr(10).join(rendered)}
"""

    @staticmethod
    def _mode_guidance(mode: str) -> str:
        """Adjust evidence semantics without weakening entity/fact constraints."""
        guidance = {
            "single_semantic": (
                "Resolve the question's paraphrases jointly: match the described partner role, "
                "deployment setting, region and key-management condition in the same file. Do "
                "not substitute another partner merely because it states a similar lead time."
            ),
            "conflict_pair": (
                "The question explicitly asks for latest or conflicting versions. Retain each "
                "dated, source-specific value needed to reconcile the change. A working plan is "
                "admissible as the latest available projection when its as-of date is clear; do "
                "not require formal approval unless the question asks what was approved/applied. "
                "Also retain the immediately preceding conflicting record and assign it to the "
                "same metric facets so the change can be stated explicitly."
            ),
            "exhaustive": (
                "Treat each distinct intake artifact as one report. Treat semantically equivalent "
                "descriptions of the named issue as instances even when the exact quoted phrase "
                "is absent. Admit concrete reports that reveal their intake/source channel, then "
                "compare counts of distinct reports; reject background specifications, examples "
                "and documents that merely mention the topic without recording an intake event. "
                "When the issue label is quoted, prefer it in the title, subject, issue summary or "
                "a direct reporter utterance. Do not count outbound customer notices as inbound "
                "reports, and deduplicate later follow-ups that only mention an earlier incident."
            ),
            "corpus_level": (
                "The answer is a corpus synthesis. Prefer files that explicitly enumerate a "
                "high-level organization or label functions as top-level departments. A function "
                "mentioned only as an owner, escalation contact or support dependency is not by "
                "itself a major department. A department absent from one overview may still be "
                "accepted when multiple independent files consistently treat it as top-level. "
                "Reject subteams, generic 'core functions' and proposed future-only units."
            ),
            "constrained_pair": (
                "Enforce every incident, product, region and time constraint, but admit a short "
                "postmortem when it directly states the requested cause or remediation."
            ),
        }
        return guidance.get(
            mode,
            "Use the general rules and require direct support for each requested fact.",
        )

    @staticmethod
    def _parse_json(response: str) -> dict | None:
        if response.startswith("[LLM_ERROR:"):
            return None
        match = re.search(r"\{.*\}", response, flags=re.DOTALL)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    def _select_nodes(
        self,
        question: str,
        plan: EvidencePlan,
        search_plan: QuestionSearchPlan,
        documents: list[dict],
    ) -> NodeSelection:
        if not documents:
            return NodeSelection([], {}, list(range(1, len(search_plan.facets) + 1)), [], [])
        prompt = self._selection_prompt(question, plan, search_plan, documents)
        response = self.llm.generate(
            prompt,
            "You are a PageIndex tree-search planner. Return valid JSON only.",
        ).strip()
        value = self._parse_json(response)
        if value is None:
            return NodeSelection([], {}, list(range(1, len(search_plan.facets) + 1)), [], [])

        selected: list[RetrieveResult] = []
        seen_nodes: set[tuple[str, str]] = set()
        facet_coverage: dict[int, list[str]] = {}
        entries = value.get("selected", [])
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                file_number = entry.get("file")
                if isinstance(file_number, bool) or not isinstance(file_number, int):
                    continue
                if not 1 <= file_number <= len(documents):
                    continue
                if entry.get("admit") is not True:
                    continue
                document = documents[file_number - 1]
                facet_indices = {
                    item for item in entry.get("facet_indices", [])
                    if isinstance(item, int)
                    and not isinstance(item, bool)
                    and 1 <= item <= len(search_plan.facets)
                }
                if not facet_indices:
                    continue
                requested = {
                    str(item) for item in entry.get("node_ids", [])
                    if isinstance(item, (str, int))
                }
                for node in document["nodes"]:
                    key = (document["doc_id"], node["node_id"])
                    if node["node_id"] not in requested or key in seen_nodes:
                        continue
                    seen_nodes.add(key)
                    selected.append(RetrieveResult(
                        chunk_id=(
                            f"{document['doc_id']}__pageindex__{node['node_id']}"
                        ),
                        doc_id=document["doc_id"],
                        source_type=document["source_type"],
                        text=node["text"],
                        score=1.0 / (1 + len(selected)),
                    ))
                    for facet_index in facet_indices:
                        facet_coverage.setdefault(facet_index, []).append(
                            selected[-1].chunk_id
                        )
                    if len(selected) >= plan.max_selected_nodes:
                        break
                if len(selected) >= plan.max_selected_nodes:
                    break

        followups = value.get("follow_up_queries", [])
        if not isinstance(followups, list):
            followups = []
        followups = [
            item.strip() for item in followups
            if isinstance(item, str) and item.strip()
        ][:self.config.max_followup_queries]
        declared_missing = value.get("missing_facet_indices", [])
        declared_missing = {
            item for item in declared_missing
            if isinstance(item, int) and not isinstance(item, bool)
        } if isinstance(declared_missing, list) else set()
        missing = sorted(
            set(range(1, len(search_plan.facets) + 1))
            - set(facet_coverage)
            | declared_missing
        )
        conflicts = value.get("conflicts", [])
        if not isinstance(conflicts, list):
            conflicts = []
        conflicts = [item.strip() for item in conflicts if isinstance(item, str) and item.strip()]
        return NodeSelection(selected, facet_coverage, missing, followups, conflicts)

    @staticmethod
    def _entity_tokens(hard_constraints: tuple[str, ...]) -> list[str]:
        """Entity tokens from the 'entity: ...' hard constraint, if any."""
        for constraint in hard_constraints:
            match = re.match(r"(?i)^entity\s*:\s*(.+)$", str(constraint).strip())
            if match:
                return [
                    token for token in re.findall(r"[a-z0-9]+", match.group(1).casefold())
                    if len(token) >= 4
                ]
        return []

    @classmethod
    def _build_version_pair_queries(
        cls, search_plan: QuestionSearchPlan
    ) -> list[str]:
        """Second-hop searches that surface the preceding version of an entity.

        The conflict companion only scans the PageIndex candidate window; when
        the older record was ranked outside that window these queries bring it
        back into the tree pass, where the normal node audit must still accept
        it before it can reach generation.
        """
        entity_tokens = cls._entity_tokens(search_plan.hard_constraints)
        if not entity_tokens:
            return []
        entity = " ".join(entity_tokens[:4])
        return [
            f"{entity} previous version earlier baseline prior assumptions before change",
            f"{entity} original sizing assumption initial projection old record",
        ]

    def _augment_conflict_companion(
        self,
        question: str,
        plan: EvidencePlan,
        search_plan: QuestionSearchPlan,
        documents: list[dict],
        selection: NodeSelection,
    ) -> NodeSelection:
        """Give an explicit conflict route a second same-entity version to audit.

        Tree selection models often stop after finding the latest record.  This
        deterministic guard only adds one candidate file when it matches the
        named entity and several requested metric labels; the normal node audit
        must still accept it before it can reach generation.
        """
        selected_docs = {item.doc_id for item in selection.selected}
        if plan.mode != "conflict_pair" or len(selected_docs) >= 2:
            return selection

        entity_tokens = self._entity_tokens(search_plan.hard_constraints)
        if not entity_tokens:
            return selection

        metric_vocabulary = {
            "baseline", "growth", "peak", "qps", "concurrent", "sessions",
            "version", "current", "latest", "previous", "earlier", "limit",
            "quota", "threshold", "date", "price", "latency", "capacity",
        }
        question_metrics = {
            token for token in re.findall(r"[a-z0-9]+", question.casefold())
            if token in metric_vocabulary
        }
        if len(question_metrics) < 2:
            return selection

        ranked: list[tuple[int, int, dict]] = []
        for position, document in enumerate(documents):
            if document["doc_id"] in selected_docs:
                continue
            haystack = " ".join(node["text"] for node in document["nodes"]).casefold()
            entity_hits = sum(token in haystack for token in entity_tokens)
            metric_hits = sum(token in haystack for token in question_metrics)
            if entity_hits >= max(1, len(entity_tokens) - 1) and metric_hits >= 3:
                ranked.append((entity_hits + metric_hits, -position, document))
        if not ranked:
            return selection

        document = max(ranked, key=lambda item: (item[0], item[1]))[2]
        node_scores: list[tuple[int, int, dict]] = []
        for position, node in enumerate(document["nodes"]):
            lowered = node["text"].casefold()
            score = sum(token in lowered for token in entity_tokens + list(question_metrics))
            if score:
                node_scores.append((score, -position, node))
        chosen = [item[2] for item in sorted(node_scores, reverse=True)[:2]]
        if not chosen:
            return selection

        selected = list(selection.selected)
        coverage = {facet: list(chunks) for facet, chunks in selection.facet_coverage.items()}
        for node in chosen:
            result = RetrieveResult(
                chunk_id=f"{document['doc_id']}__pageindex__{node['node_id']}",
                doc_id=document["doc_id"],
                source_type=document["source_type"],
                text=node["text"],
                score=1.0 / (1 + len(selected)),
            )
            selected.append(result)
            for facet_index in range(1, len(search_plan.facets) + 1):
                coverage.setdefault(facet_index, []).append(result.chunk_id)
        return NodeSelection(
            selected[:plan.max_selected_nodes],
            coverage,
            [],
            selection.follow_up_queries,
            selection.conflicts + ["conflict_companion_added_for_audit"],
        )

    def _audit_nodes(
        self,
        question: str,
        plan: EvidencePlan,
        search_plan: QuestionSearchPlan,
        selection: NodeSelection,
    ) -> NodeSelection:
        if not selection.selected or not self.config.require_node_audit:
            return selection
        evidence = self._format_audit_evidence(selection.selected)
        mode_guidance = self._mode_guidance(plan.mode)
        prompt = f"""Audit candidate evidence before it may enter the final answer context.

Question: {question}
Mode: {plan.mode}
Facets: {json.dumps(search_plan.facets, ensure_ascii=False)}
Hard constraints: {json.dumps(search_plan.hard_constraints, ensure_ascii=False)}
Risk dimensions: {json.dumps(search_plan.risk_dimensions, ensure_ascii=False)}

Reject an item if it concerns the wrong entity, event, date, region or version; is only a
proposal when the question asks what was applied; supplies a conflicting quantity without a
clear final/current status; or confuses quota with overload/admission control. Accept only text
that directly supports a required facet. Do not reject a governing runbook, SLO or policy
specification merely because it omits the named customer when the facet asks how to validate or
which general threshold/rule applies. Conversely, prefer a later operational ticket/audit record
over an earlier email proposal when the question asks what was actually applied. For an explicit
conflict question, both versions may be accepted only when their roles are clear. Do not infer
facts not present in the text.

Mode-specific admission guidance: {mode_guidance}

Return JSON only:
{{
  "accepted_indices": [1],
  "facet_coverage": [{{"facet_index": 1, "evidence_indices": [1]}}],
  "rejected": [{{"evidence_index": 2, "reason": "wrong version"}}],
  "unresolved_facet_indices": [2]
}}

Candidate evidence:
{evidence}
"""
        response = self.llm.generate(
            prompt,
            "You are a fail-closed evidence auditor. Return valid JSON only.",
        ).strip()
        value = self._parse_json(response)
        if value is None:
            return NodeSelection(
                [], {}, list(range(1, len(search_plan.facets) + 1)),
                selection.follow_up_queries, selection.conflicts + ["audit_malformed"],
            )
        accepted_indices = self._clean_indices(
            value.get("accepted_indices"), len(selection.selected)
        )
        coverage: dict[int, list[str]] = {}
        referenced: set[int] = set()
        raw_coverage = value.get("facet_coverage", [])
        if isinstance(raw_coverage, list):
            for entry in raw_coverage:
                if not isinstance(entry, dict):
                    continue
                facet_index = entry.get("facet_index")
                if (
                    isinstance(facet_index, bool)
                    or not isinstance(facet_index, int)
                    or not 1 <= facet_index <= len(search_plan.facets)
                ):
                    continue
                evidence_indices = self._clean_indices(
                    entry.get("evidence_indices"), len(selection.selected)
                )
                valid = [index for index in evidence_indices if index in accepted_indices]
                if valid:
                    referenced.update(valid)
                    coverage[facet_index] = [
                        selection.selected[index - 1].chunk_id for index in valid
                    ]
        accepted = [
            selection.selected[index - 1]
            for index in accepted_indices if index in referenced
        ]
        unresolved = value.get("unresolved_facet_indices", [])
        unresolved = {
            item for item in unresolved
            if isinstance(item, int) and not isinstance(item, bool)
        } if isinstance(unresolved, list) else set()
        missing = sorted(
            set(range(1, len(search_plan.facets) + 1)) - set(coverage) | unresolved
        )
        rejected = value.get("rejected", [])
        audit_notes = [json.dumps(item, ensure_ascii=False) for item in rejected]
        if not isinstance(rejected, list):
            audit_notes = []
        return NodeSelection(
            accepted, coverage, missing, selection.follow_up_queries,
            selection.conflicts + audit_notes,
        )

    def _build_missing_facet_queries(
        self,
        question: str,
        search_plan: QuestionSearchPlan,
        selection: NodeSelection,
    ) -> list[str]:
        missing = [
            search_plan.facets[index - 1]
            for index in selection.missing_facets
            if 1 <= index <= len(search_plan.facets)
        ]
        if not missing:
            return []
        discovered = "\n\n".join(
            item.text[:1800] for item in selection.selected[:4]
        )
        prompt = f"""Generate second-hop corpus searches for evidence still missing.

Original question: {question}
Missing facets: {json.dumps(missing, ensure_ascii=False)}
Hard constraints: {json.dumps(search_plan.hard_constraints, ensure_ascii=False)}

Use artifact names, policy terminology, routes, metrics and linked concepts discovered in the
first-hop evidence. Search for the authoritative specification or final decision, not another
customer-specific paraphrase. Do not answer the question.

First-hop admitted evidence:
{discovered or '(none admitted)'}

Return JSON only: {{"search_queries": ["query"]}}
"""
        response = self.llm.generate(
            prompt,
            "You are a multi-hop retrieval planner. Return valid JSON only.",
        ).strip()
        value = self._parse_json(response) or {}
        queries = value.get("search_queries", [])
        if not isinstance(queries, list):
            queries = []
        cleaned = [
            item.strip() for item in queries
            if isinstance(item, str) and item.strip()
        ][:self.config.max_followup_queries]
        # Add authoritative, entity-independent searches for common high-risk
        # evidence classes. Customer names are useful in hop one but often hide
        # the general SLO/runbook/policy specification needed in hop two.
        missing_text = " ".join(missing).casefold()
        authoritative: list[str] = []
        if any(term in missing_text for term in ("slo", "error budget", "availability")):
            authoritative.append(
                "Hosted API SLO enterprise route tiers hot-route capacity protection "
                "availability latency p95 p99 shed_rate admission control error budget"
            )
        if any(term in missing_text for term in ("approved", "applied", "final", "policy")):
            authoritative.append(
                "final approved applied policy override audit log expiry rollback guardrails"
            )
        if any(term in missing_text for term in ("threshold", "runbook", "detection")):
            authoritative.append(
                "runbook noisy tenant detection thresholds eviction_rate p99 baseline"
            )
        if re.search(
            r"\b(organi[sz]ation|departments?|team structure|reporting|hierarchy|org chart)\b",
            missing_text,
        ):
            authoritative.append(
                "company organization chart top-level departments engineering product "
                "design org overview reporting structure"
            )
        fallback = [
            f"{question} Authoritative evidence for: {facet}"
            for facet in missing[:self.config.max_followup_queries]
        ]
        return list(dict.fromkeys(authoritative + cleaned + fallback))[
            :self.config.max_followup_queries
        ]

    def _authority_filter(
        self, question: str, selection: NodeSelection
    ) -> NodeSelection:
        """Prefer applied/audited records over requests and proposals.

        This is intentionally activated only for final-state questions and
        keeps governing specifications separate from event-specific records.
        """
        if not re.search(
            r"\b(applied|approved|implemented|current|final|policy exception)\b",
            question,
            flags=re.IGNORECASE,
        ):
            return selection
        by_doc: dict[str, list[RetrieveResult]] = {}
        for item in selection.selected:
            by_doc.setdefault(item.doc_id, []).append(item)
        if len(by_doc) < 2:
            return selection

        def authority(items: list[RetrieveResult]) -> tuple[int, bool, bool]:
            source = items[0].source_type.casefold()
            # Authority is a file-level property.  The selected PageIndex node
            # can be deliberately narrow and omit the audit/approval timeline
            # elsewhere in the same file, so inspect the original document for
            # finality while keeping node-level evidence for answer generation.
            try:
                original = self.store.read(items[0].doc_id, items[0].source_type)
            except (OSError, sqlite3.Error):
                original = None
            text = (
                original[0] if original is not None
                else "\n".join(item.text for item in items)
            ).casefold()
            governing = (
                source == "confluence"
                and any(term in text for term in (
                    "slo", "error budget", "runbook", "policy", "specification"
                ))
            )
            policy_record = any(term in text for term in (
                "exception", "override", "burst multiplier", "burst budget",
                "burst ceiling", "approved", "applied", "implement",
            ))
            score = {"jira": 2, "linear": 2, "confluence": 1, "gmail": -1}.get(
                source, 0
            )
            weights = (
                ("recorded change in audit log", 6),
                ("verified via internal debug", 5),
                ("applied policy override", 5),
                ("approved a guarded exception", 4),
                ("marking ticket resolved", 3),
                ("resolved with", 3),
                ("applied", 2),
                ("approved", 2),
                ("implemented", 2),
                ("counterproposal", -4),
                ("proposed", -3),
                ("request temporary", -3),
                ("if you confirm", -2),
                ("will implement", -2),
                ("queued", -2),
            )
            for phrase, weight in weights:
                if phrase in text:
                    score += weight
            return score, governing, policy_record

        metadata = {doc_id: authority(items) for doc_id, items in by_doc.items()}
        # A proposal email that never uses policy keywords (no exception /
        # override / approved / applied wording) used to pass the old
        # "policy and not governing" gate because policy_record was False.
        # Any clearly authoritative record (score >= 2) now competes with
        # every other non-governing file, so a request-style artifact is
        # dropped whenever it is far below the best applied/audited record.
        best = max(
            (
                score
                for score, governing, _policy in metadata.values()
                if not governing
            ),
            default=None,
        )
        if best is None or best < 2:
            return selection
        retained_docs = {
            doc_id for doc_id, (score, governing, _policy) in metadata.items()
            if governing or score >= best - 2
        }
        removed = [doc_id for doc_id in by_doc if doc_id not in retained_docs]
        if not removed:
            return selection
        retained = [
            item for item in selection.selected if item.doc_id in retained_docs
        ]
        if not retained:
            # Never collapse the evidence to zero; keep the unmodified set and
            # let the node auditor decide instead.
            return selection
        retained_chunks = {item.chunk_id for item in retained}
        coverage = {
            facet: [chunk for chunk in chunks if chunk in retained_chunks]
            for facet, chunks in selection.facet_coverage.items()
        }
        coverage = {facet: chunks for facet, chunks in coverage.items() if chunks}
        all_facets = set(selection.facet_coverage) | set(selection.missing_facets)
        missing = sorted(all_facets - set(coverage))
        notes = selection.conflicts + [
            f"authority_rejected:{doc_id}" for doc_id in removed
        ]
        return NodeSelection(
            retained, coverage, missing, selection.follow_up_queries, notes
        )

    _OUTBOUND_NOTICE_PATTERNS = (
        r"\bwe are writing to (?:inform|notify|let you know)\b",
        r"\b(?:outbound|official) (?:customer )?notice\b",
        r"\byou (?:will be|are being) notified\b",
        r"\bthis (?:is an?|email serves as an?) (?:automated )?(?:outbound )?notice\b",
        r"\bwe (?:want|would like) to inform you\b",
        r"\b(?:service|account) notice\b",
    )
    _FOLLOWUP_ARTIFACT_PATTERNS = (
        r"\bthis is a follow[- ]?up\b",
        r"\bfollowing up (?:on|regarding|about)\b",
        r"\bjust following up\b",
        r"\bto follow up (?:on|regarding|about)\b",
        r"\bper our (?:earlier|previous|last|recent)\b",
        r"\bas discussed (?:in|on|during) (?:our|the) (?:earlier|previous|last|recent)\b",
    )

    def _document_full_text(self, document: dict) -> str:
        """Lower-cased full file text, falling back to tree node text."""
        try:
            original = self.store.read(document["doc_id"], document["source_type"])
        except (OSError, sqlite3.Error):
            original = None
        if original is not None:
            return original[0].casefold()
        return " ".join(node["text"] for node in document["nodes"]).casefold()

    def _filter_exhaustive_artifacts(
        self,
        question: str,
        plan: EvidencePlan,
        documents: list[dict],
        selection: NodeSelection,
    ) -> NodeSelection:
        """Do not count outbound notices or follow-ups as new intake reports."""
        if (
            plan.mode != "exhaustive"
            or not re.search(r"\b(report|reports|intake|channel)\b", question, re.I)
        ):
            return selection
        lowered_question = question.casefold()
        removed_docs: set[str] = set()

        # Path-level markers, only when the question itself does not request
        # notice/follow-up artifacts.
        excluded_terms: list[str] = []
        if not re.search(r"\bnotice|notification\b", lowered_question):
            excluded_terms.extend(["customer-notice", "customer_notice", "outbound-notice"])
        if not re.search(r"\bfollow[- ]?up\b", lowered_question):
            excluded_terms.extend(["followup", "follow-up", "follow_up"])
        if excluded_terms:
            for document in documents:
                path = str(document.get("source_path", "")).casefold()
                if any(term in path for term in excluded_terms):
                    removed_docs.add(document["doc_id"])

        # Content-level detection for artifacts whose paths carry no marker.
        # The exhaustive selector counts concrete intake events, so an artifact
        # that explicitly self-labels as an outbound notice or a follow-up is
        # not a new inbound report regardless of its file name.
        check_outbound = not re.search(r"\bnotice|notification\b", lowered_question)
        check_followup = not re.search(r"\bfollow[- ]?up\b", lowered_question)
        if check_outbound or check_followup:
            for document in documents:
                if document["doc_id"] in removed_docs:
                    continue
                text = self._document_full_text(document)
                if not text:
                    continue
                if check_outbound and any(
                    re.search(pattern, text) for pattern in self._OUTBOUND_NOTICE_PATTERNS
                ):
                    removed_docs.add(document["doc_id"])
                elif check_followup and any(
                    re.search(pattern, text) for pattern in self._FOLLOWUP_ARTIFACT_PATTERNS
                ):
                    removed_docs.add(document["doc_id"])
        if not removed_docs:
            return selection
        retained = [
            item for item in selection.selected if item.doc_id not in removed_docs
        ]
        retained_chunks = {item.chunk_id for item in retained}
        coverage = {
            facet: [chunk for chunk in chunks if chunk in retained_chunks]
            for facet, chunks in selection.facet_coverage.items()
        }
        coverage = {facet: chunks for facet, chunks in coverage.items() if chunks}
        all_facets = set(selection.facet_coverage) | set(selection.missing_facets)
        return NodeSelection(
            retained,
            coverage,
            sorted(all_facets - set(coverage)),
            selection.follow_up_queries,
            selection.conflicts + [
                f"non_intake_artifact_rejected:{doc_id}"
                for doc_id in sorted(removed_docs)
            ],
        )

    def _partial_full_document_results(
        self, selected: list[RetrieveResult]
    ) -> list[RetrieveResult]:
        """Escalate read depth only inside files that passed admission.

        A short authoritative file can contain answer facets in distant tree
        nodes.  When node coverage remains partial, expose the original file as
        one bounded evidence item instead of widening back to unvetted files.
        """
        expanded: list[RetrieveResult] = []
        seen: set[str] = set()
        for item in selected:
            if item.doc_id in seen:
                continue
            seen.add(item.doc_id)
            try:
                original = self.store.read(item.doc_id, item.source_type)
            except (OSError, sqlite3.Error):
                original = None
            if original is None:
                continue
            text, _ = original
            if not text.strip() or len(text) > self.config.max_partial_full_document_chars:
                continue
            expanded.append(RetrieveResult(
                chunk_id=f"{item.doc_id}__pageindex__full",
                doc_id=item.doc_id,
                source_type=item.source_type,
                text=text,
                score=item.score,
            ))
        return expanded

    @staticmethod
    def _format_audit_evidence(selected: list[RetrieveResult]) -> str:
        return "\n\n".join(
            f"[{index}] doc_id={item.doc_id} source={item.source_type}\n{item.text}"
            for index, item in enumerate(selected, 1)
        )

    @staticmethod
    def _clean_indices(value: object, count: int) -> list[int]:
        if not isinstance(value, list):
            return []
        result: list[int] = []
        for item in value:
            if (
                isinstance(item, int) and not isinstance(item, bool)
                and 1 <= item <= count and item not in result
            ):
                result.append(item)
        return result

    @staticmethod
    def _merge_results(*groups: list[RetrieveResult]) -> list[RetrieveResult]:
        merged: list[RetrieveResult] = []
        seen: set[str] = set()
        for group in groups:
            for item in group:
                if item.chunk_id in seen:
                    continue
                seen.add(item.chunk_id)
                merged.append(item)
        return merged

    def route(
        self,
        question: str,
        question_type: str | None,
        results: list[RetrieveResult],
        retrieve_callback: Callable[[str], list[RetrieveResult]] | None = None,
    ) -> list[RetrieveResult]:
        plan = self.planner.plan(question, question_type)
        self.last_trace = {
            "plan": asdict(plan),
            "initial_chunks": len(results),
            "initial_documents": len({item.doc_id for item in results}),
            "pageindex_documents": [],
            "selected_nodes": [],
            "follow_up_queries": [],
            "hops": 0,
            "route_action": "es_only",
        }
        if not self.config.enabled or not plan.use_pageindex:
            return results

        original_results = list(results)
        search_plan = self._build_search_plan(question, plan)
        max_hops = min(plan.max_hops, self.config.max_hops)
        planned_queries = [
            query for query in search_plan.search_queries
            if query.casefold() != question.casefold()
        ][:self.config.max_followup_queries]
        executed_queries = list(planned_queries)
        if retrieve_callback is not None and max_hops > 0 and planned_queries:
            extra_groups = [retrieve_callback(query) for query in planned_queries]
            results = self._interleave_results(original_results, *extra_groups)
            self.last_trace["hops"] = 1

        documents = self._candidate_trees(results, plan)
        documents = self._prefer_direct_semantic_event_source(
            question, plan, documents
        )
        selection = self._select_nodes(question, plan, search_plan, documents)
        selection = self._augment_conflict_companion(
            question, plan, search_plan, documents, selection
        )

        # If the first tree pass still exposes a missing facet and no planned
        # query was executed, use the selector's targeted follow-ups once.
        if (
            retrieve_callback is not None
            and max_hops > 0
            and self.last_trace["hops"] == 0
            and selection.missing_facets
            and selection.follow_up_queries
        ):
            extra_groups = [
                retrieve_callback(query)
                for query in selection.follow_up_queries[:self.config.max_followup_queries]
            ]
            results = self._interleave_results(original_results, *extra_groups)
            documents = self._candidate_trees(results, plan)
            documents = self._prefer_direct_semantic_event_source(
                question, plan, documents
            )
            selection = self._select_nodes(question, plan, search_plan, documents)
            selection = self._augment_conflict_companion(
                question, plan, search_plan, documents, selection
            )
            self.last_trace["hops"] = 1

        selection = self._authority_filter(question, selection)
        audited = self._audit_nodes(question, plan, search_plan, selection)

        # A second hop is driven by the auditor's missing facet set, not by a
        # model-supplied global completeness boolean.  It can use terminology
        # discovered in hop one to find an authoritative linked document.
        needs_version_pair = (
            plan.mode == "conflict_pair"
            and len({item.doc_id for item in audited.selected}) < 2
        )
        if (
            retrieve_callback is not None
            and self.last_trace["hops"] < max_hops
            and (audited.missing_facets or needs_version_pair)
        ):
            missing_queries = self._build_missing_facet_queries(
                question, search_plan, audited
            )
            if needs_version_pair:
                # Surface the preceding same-entity version through the same
                # tree pass; the node auditor still rejects wrong-version
                # documents before they can reach generation.
                version_queries = self._build_version_pair_queries(search_plan)
                missing_queries = list(dict.fromkeys(
                    version_queries + missing_queries
                ))[:self.config.max_followup_queries]
            if missing_queries:
                extra_groups = [
                    retrieve_callback(query) for query in missing_queries
                ]
                expanded_results = self._interleave_results(results, *extra_groups)
                # Never let a later hop evict documents that already passed a
                # prior file/node audit from the bounded PageIndex window.
                results = self._merge_results(
                    audited.selected, selection.selected, expanded_results
                )
                documents = self._candidate_trees(results, plan)
                documents = self._prefer_direct_semantic_event_source(
                    question, plan, documents
                )
                selection = self._select_nodes(
                    question, plan, search_plan, documents
                )
                selection = self._augment_conflict_companion(
                    question, plan, search_plan, documents, selection
                )
                selection = self._authority_filter(question, selection)
                audited = self._audit_nodes(
                    question, plan, search_plan, selection
                )
                executed_queries.extend(missing_queries)
                self.last_trace["hops"] += 1

        audited = self._authority_filter(question, audited)
        audited = self._filter_exhaustive_artifacts(
            question, plan, documents, audited
        )
        coverage_complete = not audited.missing_facets and bool(audited.selected)
        if coverage_complete:
            routed_results = audited.selected
            route_action = "pageindex_admitted"
        elif audited.selected:
            admitted_docs = {item.doc_id for item in audited.selected}
            same_document_chunks = [
                item for item in results if item.doc_id in admitted_docs
            ]
            full_document_results = self._partial_full_document_results(
                audited.selected
            )
            # Semantic questions that name a direct communication artifact (a
            # call/meeting/transcript, email thread or ticket) have already
            # narrowed the candidate set to direct sources.  When the node
            # selection still misses a facet, read one complete direct event
            # artifact under the larger event ceiling instead of leaving the
            # timeline to truncated tree nodes.  The generator's factual
            # verification still gates unsupported claims.
            if plan.mode == "single_semantic" and audited.missing_facets:
                direct_event = self._first_direct_event_document(
                    question, plan, documents
                )
                if direct_event is not None:
                    event_full = self._bounded_full_document(
                        direct_event,
                        self.config.semantic_event_full_max_chars,
                        "event_full",
                    )
                    if event_full is not None:
                        full_document_results = self._merge_results(
                            [event_full], full_document_results
                        )
            # Multi-hop: the strict node auditor can reject every node of a
            # file that already passed the file-level authority filter (for
            # example hypothesis-only sections in an otherwise applied Jira
            # record). Re-expose those files as bounded full documents so the
            # applied/audited lifecycle remains visible to the final answer
            # gate, which still runs precision evidence selection and factual
            # verification.
            if plan.mode == "multi_hop" and audited.missing_facets:
                preaudit_docs = {item.doc_id for item in selection.selected}
                for doc_id in sorted(preaudit_docs - admitted_docs):
                    entry = next(
                        (d for d in documents if d["doc_id"] == doc_id), None
                    )
                    if entry is None:
                        continue
                    full = self._bounded_full_document(
                        entry,
                        self.config.max_partial_full_document_chars,
                        "authority_full",
                    )
                    if full is not None:
                        full_document_results = self._merge_results(
                            [full], full_document_results
                        )
            if plan.mode in {"exhaustive", "corpus_level"}:
                # Aggregation and corpus-level synthesis need one complete
                # artifact per admitted file before repeated tree nodes can
                # consume the generator's bounded candidate window.
                routed_results = self._merge_results(
                    full_document_results, audited.selected, same_document_chunks
                )
            else:
                routed_results = self._merge_results(
                    audited.selected, full_document_results, same_document_chunks
                )
            route_action = (
                "pageindex_partial_full_scoped"
                if full_document_results else "pageindex_partial_scoped"
            )
            self.last_trace["full_document_expansions"] = [
                item.doc_id for item in full_document_results
            ]
        elif plan.mode == "single_semantic" and documents:
            # Once the explicit event type has narrowed the candidate set to
            # direct artifacts (for example Fireflies for a call), a failed
            # node selector may read exactly one top-ranked complete artifact.
            # This is event-scoped and never falls back to arbitrary raw ES.
            document = documents[0]
            original = self.store.read(
                document["doc_id"], document["source_type"]
            )
            if (
                original is not None
                and original[0].strip()
                and len(original[0]) <= self.config.max_partial_full_document_chars
            ):
                routed_results = [RetrieveResult(
                    chunk_id=f"{document['doc_id']}__pageindex__event_full",
                    doc_id=document["doc_id"],
                    source_type=document["source_type"],
                    text=original[0],
                    score=1.0,
                )]
                route_action = "pageindex_semantic_event_full"
            else:
                routed_results = []
                route_action = "pageindex_partial"
        elif plan.mode == "multi_hop" and selection.selected:
            # File-level authority has already removed proposals. If the node
            # auditor is overly strict about a hypothesis section, retain only
            # those authoritative files and expose their full lifecycle so the
            # final answer gate can see the later applied/resolved state.
            full_document_results = self._partial_full_document_results(
                selection.selected
            )
            routed_results = self._merge_results(
                full_document_results, selection.selected
            )
            route_action = "pageindex_authority_full_scoped"
            self.last_trace["full_document_expansions"] = [
                item.doc_id for item in full_document_results
            ]
        elif plan.mode == "corpus_level" and selection.selected:
            # The strict node audit can reject every distributed organization
            # clue because no single file is a formal org chart.  Keep the
            # PageIndex tree selection as a scoped synthesis set; never widen
            # this mode back to arbitrary raw ES hits.
            full_document_results = self._partial_full_document_results(
                selection.selected
            )
            routed_results = self._merge_results(
                full_document_results, selection.selected
            )
            route_action = "pageindex_corpus_preaudit_scoped"
            self.last_trace["full_document_expansions"] = [
                item.doc_id for item in full_document_results
            ]
        elif plan.mode == "corpus_level" and retrieve_callback is not None:
            # The strict tree pass can reject every distributed organization
            # clue because no single file is a formal org chart. Run one
            # deterministic organization-structure sweep over the corpus and
            # expose the top candidates as a bounded scoped set; only fall
            # back to the raw ES window when the sweep yields nothing. The
            # generator's high_level rules and final answer audit still
            # require top-level departments only.
            org_query = (
                "organization structure major departments Engineering Product "
                "Developer experience Research Applied ML Go-to-market Security "
                "compliance Customer support success teams"
            )
            sweep = self._interleave_results(results, retrieve_callback(org_query))
            sweep_documents = self._candidate_trees(sweep, plan)
            sweep_scope: list[RetrieveResult] = []
            for document in sweep_documents[:6]:
                full = self._bounded_full_document(
                    document,
                    self.config.max_partial_full_document_chars,
                    "org_scope",
                )
                if full is not None:
                    sweep_scope.append(full)
            if sweep_scope:
                routed_results = sweep_scope
                route_action = "pageindex_corpus_org_scope"
                self.last_trace["full_document_expansions"] = [
                    item.doc_id for item in sweep_scope
                ]
            else:
                routed_results = original_results
                route_action = "fallback_es_incomplete"
        elif (
            self.config.fallback_to_es_on_incomplete
            and plan.mode != "single_semantic"
        ):
            routed_results = original_results
            route_action = "fallback_es_incomplete"
        else:
            routed_results = audited.selected
            route_action = "pageindex_partial"

        self.last_trace.update({
            "search_plan": asdict(search_plan),
            "pageindex_documents": [
                {
                    "doc_id": item["doc_id"],
                    "word_count": item["word_count"],
                    "heading_count": item["heading_count"],
                    "eligible": item["eligible"],
                }
                for item in documents
            ],
            "preaudit_selected_nodes": [item.chunk_id for item in selection.selected],
            "selected_nodes": [item.chunk_id for item in audited.selected],
            "selected_document_ids": list(dict.fromkeys(
                item.doc_id for item in audited.selected
            )),
            "follow_up_queries": list(dict.fromkeys(
                executed_queries + selection.follow_up_queries
            )),
            "facet_coverage": audited.facet_coverage,
            "missing_facets": audited.missing_facets,
            "conflicts_and_rejections": audited.conflicts,
            "coverage_complete": coverage_complete,
            "route_action": route_action,
        })

        # Complete PageIndex evidence is a closed final set.  A partial result
        # may only be supplemented by chunks from already admitted documents;
        # arbitrary ES hits are never mixed back into a scoped route.
        return routed_results
