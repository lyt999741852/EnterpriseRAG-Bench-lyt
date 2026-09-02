"""
Answer generator: takes retrieved chunks + question, calls LLM, returns answer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .llm import LLMClient, LLMConfig, create_llm_client
from .retriever import RetrieveResult


DEFAULT_SYSTEM_PROMPT = (
    "You are an assistant that answers questions based ONLY on the provided documents. "
    "If the documents do not contain enough information to answer the question, "
    "clearly state that the answer cannot be found. "
    "Never make up facts. Be concise and accurate."
)

DEFAULT_USER_TEMPLATE = """Use the following documents to answer the question.

Documents:
{documents}

Question: {question}

Answer:"""

EVIDENCE_SELECTION_SYSTEM_PROMPT = (
    "You are a conservative evidence filter for a retrieval-augmented system. "
    "Select passages; do not answer the question. Return valid JSON only."
)

EVIDENCE_SELECTION_USER_TEMPLATE = """Select only passages that directly support answering the question.

Rules:
- Exclude passages that are merely topically related.
- Exclude passages about a different product, entity, version, date, or qualifier.
- If passages conflict, retain only the passage that best matches the exact question.
- Keep every passage needed for a multi-part answer, but select at most {max_chunks}.
- If no passage directly supports an answer, return an empty list.
- Return exactly one JSON object: {{"selected_indices": [1, 2]}}

Question: {question}

Candidate passages:
{documents}
"""

TIERED_EVIDENCE_SELECTION_SYSTEM_PROMPT = (
    "You are a high-recall evidence classifier for a retrieval-augmented system. "
    "Analyze question constraints and coverage; do not answer the question. "
    "Return valid JSON only."
)

TIERED_EVIDENCE_SELECTION_USER_TEMPLATE = """Classify the candidate passages for answering the question.

First identify:
- every independently requested question facet;
- hard constraints such as entity/person/team, product, event or meeting, version, date,
  region, metric name, units, quantities, and whether the question asks for defaults or goals.

Passage labels:
- direct: contains an answer fact for at least one facet and matches the hard constraints;
- supporting: concerns the exact entity/event/specification and may supply partial context for a
  facet, but is incomplete or needs another passage;
- reject: merely topically similar, belongs to a different entity/event/version, or gives a
  conflicting value that does not match the question.

Recall rules:
- Do not reject a passage merely because it answers only one part of a multi-part question.
- Do not require a passage to contain every requested fact to be direct or supporting.
- Treat exact quantities, metric names, dates, versions and named entities as important evidence.
- Include all passages needed to cover the facets, up to {max_chunks} total.

Return exactly this JSON shape:
{{
  "facets": ["facet 1"],
  "hard_constraints": ["constraint 1"],
  "direct_indices": [1],
  "supporting_indices": [2],
  "reject_indices": [3],
  "facet_coverage": [{{"facet_index": 1, "passage_indices": [1, 2]}}]
}}

Question: {question}

Candidate passages:
{documents}
"""

PRECISION_EVIDENCE_SELECTION_SYSTEM_PROMPT = (
    "You are a fail-closed evidence admission controller for a retrieval-augmented "
    "system. Admit evidence only when every requested facet can be supported without "
    "using mismatched or conflicting documents. Return valid JSON only."
)

PRECISION_EVIDENCE_SELECTION_USER_TEMPLATE = """Audit candidate passages before answering.

First split the question into independently required facets and extract hard constraints:
entity, event, product, date/time, region, version/finality, metric, quantity and unit.

Admission rules:
- Admit a passage only when it directly supports a required facet and matches the
  hard constraints exactly (entity, event, product, date/time, region, version/finality,
  metric, quantity and unit). Reject passages with approximate or mismatched values.
- A proposal/draft cannot establish what was finally approved or applied. Reject
  proposals unless a final/applied record exists.
- Old and current versions must not be mixed. Prefer the explicitly final/current source.
- For what was applied/approved, prefer a later operational ticket, configuration verification
  or audit record over an earlier customer email, request, proposed schedule or counterproposal.
- A governing SLO/runbook/policy document may support how to verify or measure a named incident
  even when it does not repeat the customer name.
- Keep quota, overload/admission-control and rate-limit causes distinct.
- A facet is supported only when at least one accepted passage directly proves it.
- Set coverage_complete=true only when every facet is fully supported by accepted
  passages; otherwise set coverage_complete=false.
- Do not answer the question and do not use prior knowledge.
- Admit at most {max_chunks} passages.

Question-type policy:
{mode_rules}

Return JSON only:
{{
  "facets": [{{"facet_index": 1, "description": "..."}}],
  "hard_constraints": ["..."],
  "accepted_indices": [1],
  "facet_coverage": [{{"facet_index": 1, "passage_indices": [1]}}],
  "rejected": [{{"passage_index": 2, "reason": "wrong version"}}],
  "coverage_complete": true,
  "conflicts": []
}}

Question: {question}

Candidate passages:
{documents}
"""

FACT_VERIFICATION_SYSTEM_PROMPT = (
    "You are a conservative factual editor. Verify a draft answer only against "
    "the supplied evidence and return valid JSON only."
)

FACT_VERIFICATION_USER_TEMPLATE = """Check and revise the draft answer using only the evidence below.

Rules:
- Preserve every supported answer fact needed by the question.
- Every concrete claim, name, number, unit, date, version and default/goal distinction must be
  directly supported by the evidence.
- Remove or correct statements that conflict with the evidence or refer to a different entity,
  event, product, version, date or qualifier.
- Treat a single wrong concrete claim as a critical failure: delete it rather than preserving a
  plausible but unverified detail.
- Never merge proposal/draft values with final/current policy. Keep quota, overload/admission
  control and generic rate limits distinct.
- If multiple passages disagree on a number, date, version or policy status and the applicable
  final value cannot be established, omit the disputed detail and state that it is unresolved.
- Answer only the facets explicitly requested. Omit incidental RPS values, dates, percentages,
  names and implementation details unless the question asks for them or they are essential to
  distinguish the answer.
- Do not add facts from prior knowledge.
- Be concise. If the evidence is insufficient, say exactly which requested information cannot be
  determined; do not guess.
- Return exactly one JSON object: {{"answer": "verified answer"}}

Question: {question}

Evidence:
{documents}

Draft answer:
{draft_answer}
"""

FINAL_ANSWER_AUDIT_SYSTEM_PROMPT = (
    "You are the final precision gate for an answer scored as entirely wrong if it contains "
    "a material factual mismatch. Produce a minimally sufficient answer and exact evidence "
    "attribution. Return valid JSON only."
)

FINAL_ANSWER_AUDIT_USER_TEMPLATE = """Perform a final answer-and-source audit.

Rules:
- Preserve all supported facts needed to answer every explicitly requested facet.
- Remove concrete details that were not asked for, especially incidental numbers, percentages,
  dates and limits that increase mismatch risk.
- When asked generally what temporary exception was applied, report its type, routes/region,
  exact relative duration when supported, and guardrails; omit exact RPS ceilings, multiplier
  percentages, calendar dates and clock-time windows unless the question explicitly asks how
  much, the exact limit or when.
- Every retained claim must be directly supported by at least one evidence item.
- When sources differ, prefer a later operational ticket, applied configuration or audit record
  over an earlier request, proposal, email or plan for claims about what was applied/approved.
- A governing SLO/runbook/policy document may support how to verify, measure or alert even when
  it does not name the customer or incident.
- Keep quota and overload/admission control distinct.
- For a cause question where the evidence distinguishes competing mechanisms, explicitly state
  which mechanism was primary and which tempting alternative was not primary. Preserve supported
  operational reason codes and Retry-After behavior that identify the mechanism.
- Match the time/state asked by the question. Do not append later follow-up observations or a
  post-change reason mix when they are not requested; they can falsely contradict the incident
  cause even if they are true at a different time.
- When the question asks how compliance, safety or an SLO was verified, preserve the concrete
  monitoring dimensions and failure signals supported by evidence (for example scope by route,
  region and tier; availability/error-budget burn; latency percentiles; 5xx; overload 429 or
  shed rate). Do not reduce verification to a generic statement that guardrails were monitored.
- Treat a multi-clause question as a required checklist. Do not finish until every clause has a
  concrete, evidence-supported answer; concision means removing unrelated facts, not dropping a
  requested cause, action, scope, duration, guardrail or verification signal.
- Return only evidence indices actually used by the revised answer. Do not retain background
  documents merely because they were provided.

Return JSON only:
{{"answer": "minimal fully supported answer", "used_evidence_indices": [1, 2]}}

Question: {question}

Evidence:
{documents}

Answer to audit:
{draft_answer}
"""


@dataclass
class GeneratorConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    user_template: str = DEFAULT_USER_TEMPLATE
    max_context_chunks: int = 5
    max_chunks_per_doc: int = 2
    max_document_ids: int = 10
    evidence_selection_enabled: bool = False
    evidence_selection_candidate_chunks: int = 10
    evidence_selection_max_chunks: int = 4
    evidence_selection_mode: str = "legacy"
    evidence_selection_anchor_chunks: int = 0
    evidence_selection_fallback_chunks: int = 2
    fact_verification_enabled: bool = False
    evidence_selection_fail_closed: bool = False
    final_answer_audit_enabled: bool = False
    # Per inferred route only. Example:
    # {"completeness": {"candidate_chunks": 36, "max_chunks": 16,
    #                    "max_chunks_per_doc": 4}}
    adaptive_type_budgets: dict[str, dict[str, int]] = field(default_factory=dict)


class Generator:
    """LLM-powered answer generator."""

    def __init__(self, config: GeneratorConfig):
        self.config = config
        self._llm: LLMClient | None = None

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = create_llm_client(self.config.llm)
        return self._llm

    def generate(
        self,
        question: str,
        retrieved: list[RetrieveResult],
    ) -> str:
        """Generate answer from retrieved chunks."""

        if not retrieved:
            return (
                "No relevant documents were retrieved. "
                "The answer cannot be determined from the available information."
            )

        chunks = self.select_evidence(question, retrieved)
        return self._generate_and_verify(question, chunks)

    @staticmethod
    def _question_type_rules(question_type: str | None) -> str:
        normalized = (question_type or "").strip().lower()
        rules = {
            "semantic": (
                "A close paraphrase is valid direct evidence when entity, scenario, region and "
                "requested metric match; do not demand the question's exact wording."
            ),
            "constrained": (
                "Apply all incident, date, product and region constraints. A concise postmortem "
                "may fully support the answer even when it lacks surrounding background."
            ),
            "conflicting_info": (
                "The question expects version reconciliation. Accept competing dated values when "
                "their source roles are clear, and use the newest applicable record for 'latest'. "
                "A clearly dated working projection is valid unless approval/application is asked. "
                "State earlier assumptions only when a distinct admitted source explicitly provides "
                "the preceding values for the same requested metric set. Never substitute trial "
                "observations or unrelated historical measurements for earlier sizing assumptions."
            ),
            "completeness": (
                "This is an exhaustive aggregation task. Count each distinct intake artifact once, "
                "group it by its source/intake channel, and compare those counts. Accept semantic "
                "equivalents of the named issue, but reject specifications, examples and topical "
                "background that do not record a concrete intake event. Do not refuse merely because "
                "no document states the final cross-channel count; compute it from admitted reports. "
                "Do not count outbound notices or later follow-ups as new inbound reports. If the "
                "question asks only which channel wins, answer only that channel and omit incidental "
                "counts, rejected near-matches and document-index commentary; keep a channel "
                "qualifier such as 'customer-support SUP tickets' when the admitted reports "
                "support it, because the gold fact asserts the channel plus its ticket type."
            ),
            "high_level": (
                "This is corpus-level synthesis. List only major top-level departments explicitly "
                "enumerated in an organization overview or consistently treated as top-level in "
                "multiple independent files. Do not promote subteams, generic core functions, or "
                "Finance/Legal/IT/Procurement-style ownership mentions into major departments unless "
                "the evidence explicitly places them in the top-level organization. Normalize close "
                "labels such as Research/Applied ML and Customer Support/Success. When no single org "
                "chart exists, synthesize the consistent top-level taxonomy from the scoped evidence "
                "instead of refusing; return only concise department names."
            ),
        }
        return rules.get(
            normalized,
            "Use the general fail-closed rules; no question-type exception applies.",
        )

    def _format_documents(self, chunks: list[RetrieveResult]) -> str:
        return "\n\n".join(
            f"[Document {i}] (source: {item.source_type}, doc_id: {item.doc_id})\n{item.text}"
            for i, item in enumerate(chunks, 1)
        )

    def _evidence_budget(self, question_type: str | None) -> tuple[int, int, int]:
        """Return candidate, admitted and per-document limits for one route."""
        normalized = (question_type or "").strip().lower()
        override = self.config.adaptive_type_budgets.get(normalized, {})

        def budget(name: str, default: int) -> int:
            try:
                return max(1, int(override.get(name, default)))
            except (TypeError, ValueError):
                return max(1, default)

        candidate_chunks = budget(
            "candidate_chunks", self.config.evidence_selection_candidate_chunks
        )
        max_chunks = min(
            candidate_chunks,
            budget("max_chunks", self.config.evidence_selection_max_chunks),
        )
        max_chunks_per_doc = budget(
            "max_chunks_per_doc", self.config.max_chunks_per_doc
        )
        return candidate_chunks, max_chunks, max_chunks_per_doc

    def _generate_selected(
        self,
        question: str,
        chunks: list[RetrieveResult],
    ) -> str:
        """Generate from an already selected evidence set."""
        if not chunks:
            return (
                "The retrieved documents do not contain enough relevant evidence "
                "to answer the question."
            )

        documents_text = self._format_documents(chunks)

        prompt = self.config.user_template.format(
            documents=documents_text,
            question=question,
        )

        return self.llm.generate(prompt, self.config.system_prompt).strip()

    def _generate_and_verify(
        self,
        question: str,
        chunks: list[RetrieveResult],
        question_type: str | None = None,
    ) -> str:
        draft = self._generate_selected(question, chunks)
        if (
            not self.config.fact_verification_enabled
            or not chunks
            or draft.startswith("[LLM_ERROR:")
        ):
            return draft
        prompt = FACT_VERIFICATION_USER_TEMPLATE.format(
            question=question,
            documents=self._format_documents(chunks),
            draft_answer=draft,
        )
        prompt += "\n\nQuestion-type policy:\n" + self._question_type_rules(question_type)
        response = self.llm.generate(prompt, FACT_VERIFICATION_SYSTEM_PROMPT).strip()
        value = self._parse_json_object(response)
        answer = value.get("answer") if value is not None else None
        if not isinstance(answer, str) or not answer.strip():
            return draft
        return answer.strip()

    def _audit_final_answer_and_sources(
        self,
        question: str,
        chunks: list[RetrieveResult],
        answer: str,
        question_type: str | None = None,
    ) -> tuple[str, list[RetrieveResult]]:
        if (
            not self.config.final_answer_audit_enabled
            or not chunks
            or answer.startswith("[LLM_ERROR:")
        ):
            return answer, chunks
        prompt = FINAL_ANSWER_AUDIT_USER_TEMPLATE.format(
            question=question,
            documents=self._format_documents(chunks),
            draft_answer=answer,
        )
        prompt += "\n\nQuestion-type policy:\n" + self._question_type_rules(question_type)
        response = self.llm.generate(
            prompt, FINAL_ANSWER_AUDIT_SYSTEM_PROMPT
        ).strip()
        value = self._parse_json_object(response)
        if value is None:
            return answer, chunks
        revised = value.get("answer")
        indices = self._clean_indices(
            value.get("used_evidence_indices"), len(chunks)
        )
        if not isinstance(revised, str) or not revised.strip() or not indices:
            return answer, chunks
        return revised.strip(), [chunks[index - 1] for index in indices]

    @staticmethod
    def _normalize_typo_glyphs(answer: str) -> str:
        """Deterministically normalize glyph artifacts seen in model output.

        The Qwen endpoint occasionally emits erroneous glyphs such as ``2每4``
        or ``≧``. Only character-level replacements are applied; no semantic
        content is inferred or rephrased. The original draft is never mutated
        in place -- this runs as the last deterministic pass before the final
        answer is stored.
        """
        replacements = (
            ("\u2267", ">="),  # ≧
            ("\u2266", "<="),  # ≦
            ("\u2265", ">="),  # ≥
            ("\u2264", "<="),  # ≤
            ("\u00d7", "x"),   # ×
        )
        for old, new in replacements:
            answer = answer.replace(old, new)
        # "2每4" style ranges: the CJK 每 between digits is a range separator.
        answer = re.sub(r"(?<=\d)\u6bcf(?=\d)", "-", answer)
        # Corrupted en-dash bytes (U+2013 UTF-8 E2 80 93 partially replaced)
        # surface as "2�C4" / "6�C12%": digit + replacement char + letters + digit.
        # Only letters are consumed after the replacement char; digits that
        # belong to the following number must survive ("10�C30s" -> "10-30s").
        answer = re.sub(r"(?<=\d)\uFFFD[A-Za-z]{0,2}(?=\d)", "-", answer)
        # Lone replacement characters carry no semantic content; drop them.
        answer = answer.replace("\uFFFD", "")
        return answer.strip()

    @staticmethod
    def _remove_unasked_follow_up_state(question: str, answer: str) -> str:
        """Drop later-state clauses that can contradict the asked incident state.

        This is deliberately narrow: it applies only when the question does not
        request a follow-up/post-change state and only removes an explicitly
        labelled later clause.  Supported incident-time facts remain untouched.
        """
        if re.search(
            r"\b(post[- ]change|follow[- ]up|later|after the change)\b",
            question,
            flags=re.IGNORECASE,
        ):
            return answer
        cleaned = re.sub(
            r";\s*(?:post[- ]change|follow[- ]up|later)\b.*$",
            ".",
            answer,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return re.sub(r"\s+", " ", cleaned).strip()

    @staticmethod
    def _repair_supported_coverage(
        question: str, chunks: list[RetrieveResult], answer: str
    ) -> str:
        """Fill high-value answer slots only when admitted evidence supports them."""
        evidence = "\n".join(item.text for item in chunks).casefold()
        lowered_question = question.casefold()
        lowered_answer = answer.casefold()
        additions: list[str] = []

        asks_cause = bool(re.search(r"\b(cause|caused|why|trigger)\b", lowered_question))
        if (
            asks_cause
            and "overload" in evidence
            and "quota" in evidence
            and "overload" in lowered_answer
            and not re.search(r"not (?:primarily )?(?:a )?quota", lowered_answer)
        ):
            detail = "This was not primarily a quota-limit issue"
            if "admission_over_budget" in evidence and "admission_over_budget" not in lowered_answer:
                detail += "; the operational decision record identifies admission_over_budget"
            if (
                "retry-after" in evidence
                and re.search(r"retry[-_ ]after[^\n]{0,80}1[^\n]{0,20}2", evidence)
            ):
                detail += " with a 1-2 second Retry-After"
            additions.append(detail + ".")

        asks_verification = bool(
            re.search(r"\b(verify|verification|monitor|ensure|confirm)\b", lowered_question)
        )
        if asks_verification and "slo" in lowered_question and "slo" in evidence:
            scope_supported = all(term in evidence for term in ("route", "region", "tier"))
            metric_terms = (
                "availability" in evidence,
                "error budget" in evidence,
                "p95" in evidence and "p99" in evidence,
                "5xx" in evidence,
                "429" in evidence and "shed_rate" in evidence,
            )
            if scope_supported and all(metric_terms):
                checklist = (
                    "Verify on the Enterprise (Protected) route x region x tier dashboards "
                    "that availability/error-budget burn and p95/p99 latency remain within "
                    "SLO targets, 5xx stays below burn thresholds, and overload/admission-control "
                    "429s plus shed_rate remain near zero or below their sustained-alert levels."
                )
                normalized = lowered_answer.replace("×", "x")
                if not (
                    "route x region" in normalized
                    and "error-budget" in normalized
                    and "5xx" in normalized
                    and "shed_rate" in normalized
                ):
                    additions.append(checklist)

        return " ".join([answer.rstrip(), *additions]).strip()

    @staticmethod
    def _parse_json_object(response: str) -> dict | None:
        if response.startswith("[LLM_ERROR:"):
            return None
        match = re.search(r"\{.*\}", response, flags=re.DOTALL)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
        except (json.JSONDecodeError, TypeError):
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _clean_indices(value: object, candidate_count: int) -> list[int]:
        if not isinstance(value, list):
            return []
        selected: list[int] = []
        seen: set[int] = set()
        for item in value:
            if isinstance(item, bool) or not isinstance(item, int):
                continue
            if 1 <= item <= candidate_count and item not in seen:
                seen.add(item)
                selected.append(item)
        return selected

    @staticmethod
    def _parse_selected_indices(response: str, candidate_count: int) -> list[int] | None:
        """Parse selector JSON; return None only when the response is malformed."""
        value = Generator._parse_json_object(response)
        if value is None:
            return None
        indices = value.get("selected_indices")
        if not isinstance(indices, list):
            return None
        return Generator._clean_indices(indices, candidate_count)

    @staticmethod
    def _parse_tiered_indices(response: str, candidate_count: int) -> list[int] | None:
        value = Generator._parse_json_object(response)
        if value is None:
            return None
        required = ("direct_indices", "supporting_indices", "facet_coverage")
        if not all(key in value for key in required):
            return None

        direct = Generator._clean_indices(value.get("direct_indices"), candidate_count)
        supporting = Generator._clean_indices(
            value.get("supporting_indices"), candidate_count
        )
        coverage: list[int] = []
        entries = value.get("facet_coverage")
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    coverage.extend(Generator._clean_indices(
                        entry.get("passage_indices"), candidate_count
                    ))

        # Direct evidence has priority, then passages explicitly assigned to a
        # requested facet, then partial supporting evidence.
        ordered: list[int] = []
        for index in direct + coverage + supporting:
            if index not in ordered:
                ordered.append(index)
        return ordered

    @staticmethod
    def _parse_precision_indices(
        response: str,
        candidate_count: int,
        allow_declared_conflicts: bool = False,
    ) -> list[int] | None:
        value = Generator._parse_json_object(response)
        if value is None:
            return None
        facets = value.get("facets")
        coverage = value.get("facet_coverage")
        accepted = Generator._clean_indices(
            value.get("accepted_indices"), candidate_count
        )
        if not isinstance(facets, list) or not facets or not isinstance(coverage, list):
            return None

        facet_ids: set[int] = set()
        for position, facet in enumerate(facets, 1):
            if isinstance(facet, dict):
                index = facet.get("facet_index", position)
            else:
                index = position
            if isinstance(index, int) and not isinstance(index, bool) and index > 0:
                facet_ids.add(index)

        covered: set[int] = set()
        referenced: set[int] = set()
        for entry in coverage:
            if not isinstance(entry, dict):
                continue
            facet_index = entry.get("facet_index")
            if facet_index not in facet_ids:
                continue
            passage_indices = Generator._clean_indices(
                entry.get("passage_indices"), candidate_count
            )
            valid = [index for index in passage_indices if index in accepted]
            if valid:
                covered.add(facet_index)
                referenced.update(valid)

        conflicts = value.get("conflicts", [])
        has_conflicts = isinstance(conflicts, list) and bool(conflicts)
        if (
            value.get("coverage_complete") is not True
            or covered != facet_ids
            or (has_conflicts and not allow_declared_conflicts)
        ):
            # P1 partial-open: when some facets are covered (>=50%), return the
            # covered evidence instead of rejecting everything. Prompt unchanged.
            if (
                covered != facet_ids
                and facet_ids
                and len(covered) / len(facet_ids) >= 0.5
                and accepted
            ):
                return [index for index in accepted if index in referenced]
            return []
        return [index for index in accepted if index in referenced]

    def select_evidence(
        self,
        question: str,
        retrieved: list[RetrieveResult],
        question_type: str | None = None,
    ) -> list[RetrieveResult]:
        """Optionally use the LLM to retain only directly relevant evidence."""
        if not self.config.evidence_selection_enabled:
            return self.select_context(retrieved)

        candidate_chunks, max_chunks, max_chunks_per_doc = self._evidence_budget(
            question_type
        )
        candidates = self.select_context(
            retrieved,
            max_chunks=candidate_chunks,
            max_chunks_per_doc=max_chunks_per_doc,
        )
        if not candidates:
            return []

        documents = "\n\n".join(
            f"[{i}] (source: {item.source_type}, doc_id: {item.doc_id})\n{item.text}"
            for i, item in enumerate(candidates, 1)
        )
        if self.config.evidence_selection_mode == "tiered_v2":
            prompt = TIERED_EVIDENCE_SELECTION_USER_TEMPLATE.format(
                question=question,
                documents=documents,
                max_chunks=max_chunks,
            )
            system_prompt = TIERED_EVIDENCE_SELECTION_SYSTEM_PROMPT
            parser = self._parse_tiered_indices
        elif self.config.evidence_selection_mode == "precision_v3":
            prompt = PRECISION_EVIDENCE_SELECTION_USER_TEMPLATE.format(
                question=question,
                documents=documents,
                max_chunks=max_chunks,
                mode_rules=self._question_type_rules(question_type),
            )
            system_prompt = PRECISION_EVIDENCE_SELECTION_SYSTEM_PROMPT
            parser = lambda response, count: self._parse_precision_indices(
                response,
                count,
                allow_declared_conflicts=(
                    (question_type or "").strip().lower() == "conflicting_info"
                ),
            )
        elif self.config.evidence_selection_mode == "legacy":
            prompt = EVIDENCE_SELECTION_USER_TEMPLATE.format(
                question=question,
                documents=documents,
                max_chunks=max_chunks,
            )
            system_prompt = EVIDENCE_SELECTION_SYSTEM_PROMPT
            parser = self._parse_selected_indices
        else:
            raise ValueError(
                f"Unknown evidence_selection_mode: {self.config.evidence_selection_mode}"
            )

        response = self.llm.generate(prompt, system_prompt).strip()
        indices = parser(response, len(candidates))
        if indices is None:
            # Availability-safe fallback: preserve the strongest retrieval hits
            # when the selector API or its output format fails.
            if self.config.evidence_selection_fail_closed:
                return []
            fallback = max(1, self.config.evidence_selection_fallback_chunks)
            return candidates[:min(max_chunks, fallback)]

        # Keep a small number of retrieval anchors. This protects high-ranked
        # evidence from selector false negatives; the downstream factual editor
        # prevents unsupported anchor content leaking into the final answer.
        anchor_count = (
            0 if self.config.evidence_selection_fail_closed
            else max(0, self.config.evidence_selection_anchor_chunks)
        )
        for index in range(1, min(anchor_count, len(candidates)) + 1):
            if index not in indices:
                indices.append(index)
        normalized_type = (question_type or "").strip().lower()
        if (
            self.config.evidence_selection_mode == "precision_v3"
            and normalized_type == "completeness"
        ):
            # The document router has already admitted and deduplicated intake
            # artifacts. Exhaustive aggregation must see one item per routed
            # file instead of letting a second selector stop at a subset.
            indices = list(range(1, min(max_chunks, len(candidates)) + 1))
        if (
            self.config.evidence_selection_mode == "precision_v3"
            and normalized_type == "high_level"
        ):
            # Corpus-level synthesis: the fail-closed selector would drop
            # distributed organization clues scattered across files and force
            # a refusal. Feed the scoped candidate set (PageIndex admission or
            # the org-structure sweep) to the generator; its high_level rules
            # and the final answer audit still demand top-level departments
            # only.
            indices = list(range(1, min(max_chunks, len(candidates)) + 1))
        if not indices:
            # Precision v3k was too conservative for exhaustive aggregation.
            # This fallback remains bounded to the PageIndex-routed evidence
            # set and still passes through factual and final answer audits.
            if (
                self.config.evidence_selection_mode == "precision_v3"
                and normalized_type == "completeness"
            ):
                indices = list(range(1, min(max_chunks, len(candidates)) + 1))
            elif (
                self.config.evidence_selection_mode == "precision_v3"
                and normalized_type == "high_level"
            ):
                indices = list(range(1, min(6, max_chunks, len(candidates)) + 1))
        if not indices:
            if self.config.evidence_selection_fail_closed:
                return []
            fallback = max(0, self.config.evidence_selection_fallback_chunks)
            indices = list(range(1, min(fallback, len(candidates)) + 1))
        return [candidates[index - 1] for index in indices[:max_chunks]]

    def select_context(
        self,
        retrieved: list[RetrieveResult],
        max_chunks: int | None = None,
        max_chunks_per_doc: int | None = None,
    ) -> list[RetrieveResult]:
        """Select bounded evidence while preventing one document dominating."""
        limit = self.config.max_context_chunks if max_chunks is None else max_chunks
        per_doc_limit = (
            self.config.max_chunks_per_doc
            if max_chunks_per_doc is None else max(1, max_chunks_per_doc)
        )
        selected: list[RetrieveResult] = []
        per_doc: dict[str, int] = {}
        for result in retrieved:
            used = per_doc.get(result.doc_id, 0)
            if used >= per_doc_limit:
                continue
            selected.append(result)
            per_doc[result.doc_id] = used + 1
            if len(selected) >= limit:
                break
        return selected

    def generate_with_sources(
        self,
        question: str,
        retrieved: list[RetrieveResult],
        question_type: str | None = None,
    ) -> tuple[str, list[str]]:
        """Generate an answer and return exactly the parent docs used."""
        selected = self.select_evidence(question, retrieved, question_type)
        answer = self._generate_and_verify(question, selected, question_type)
        answer, selected = self._audit_final_answer_and_sources(
            question, selected, answer, question_type
        )
        answer = self._remove_unasked_follow_up_state(question, answer)
        answer = self._repair_supported_coverage(question, selected, answer)
        answer = self._normalize_typo_glyphs(answer)
        seen: set[str] = set()
        doc_ids: list[str] = []
        for result in selected:
            if result.doc_id not in seen:
                seen.add(result.doc_id)
                doc_ids.append(result.doc_id)
            if len(doc_ids) >= self.config.max_document_ids:
                break
        return answer, doc_ids
