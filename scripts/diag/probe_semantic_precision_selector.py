"""Replay the frozen precision-v3 evidence selector without answer generation.

This completed-run diagnostic accepts question IDs, never gold document IDs or
answer facts.  It reconstructs the selector candidates from the frozen trace,
fetches those chunks by exact ID, calls only the selector prompt, and applies
the strict parser used by the S1 run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from src.elasticsearch_backend import ElasticsearchBackend, ElasticsearchConfig
from src.generator import (
    Generator,
    PRECISION_EVIDENCE_SELECTION_SYSTEM_PROMPT,
    PRECISION_EVIDENCE_SELECTION_USER_TEMPLATE,
)
from src.llm import LLMConfig, create_llm_client


def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        question_id = str(row.get("question_id", ""))
        if not question_id or question_id in rows:
            raise ValueError(f"invalid or duplicate question_id at {path}:{line_number}")
        rows[question_id] = row
    return rows


def clean_indices(value: object, candidate_count: int) -> list[int]:
    if not isinstance(value, list):
        return []
    selected: list[int] = []
    for item in value:
        if (
            isinstance(item, int)
            and not isinstance(item, bool)
            and 1 <= item <= candidate_count
            and item not in selected
        ):
            selected.append(item)
    return selected


def parse_strict_precision(response: str, candidate_count: int) -> dict[str, Any]:
    """Apply the strict S1 precision-v3 admission contract."""
    value = Generator._parse_json_object(response)
    if value is None:
        return {"status": "malformed", "selected_indices": None}
    facets = value.get("facets")
    coverage = value.get("facet_coverage")
    accepted = clean_indices(value.get("accepted_indices"), candidate_count)
    if not isinstance(facets, list) or not facets or not isinstance(coverage, list):
        return {"status": "malformed", "selected_indices": None, "parsed": value}

    facet_ids: set[int] = set()
    for position, facet in enumerate(facets, 1):
        index = facet.get("facet_index", position) if isinstance(facet, dict) else position
        if isinstance(index, int) and not isinstance(index, bool) and index > 0:
            facet_ids.add(index)

    covered: set[int] = set()
    referenced: set[int] = set()
    for entry in coverage:
        if not isinstance(entry, dict) or entry.get("facet_index") not in facet_ids:
            continue
        valid = [
            index
            for index in clean_indices(entry.get("passage_indices"), candidate_count)
            if index in accepted
        ]
        if valid:
            covered.add(entry["facet_index"])
            referenced.update(valid)

    conflicts = value.get("conflicts", [])
    complete = (
        value.get("coverage_complete") is True
        and covered == facet_ids
        and not (isinstance(conflicts, list) and conflicts)
    )
    selected = [index for index in accepted if index in referenced] if complete else []
    return {
        "status": "accepted" if selected else "rejected",
        "selected_indices": selected,
        "accepted_indices_declared": accepted,
        "facet_ids": sorted(facet_ids),
        "covered_facet_ids": sorted(covered),
        "coverage_complete_declared": value.get("coverage_complete"),
        "conflicts_declared": conflicts,
        "parsed": value,
    }


def fetch_chunks(
    backend: ElasticsearchBackend, chunk_ids: list[str]
) -> dict[str, dict[str, Any]]:
    response = backend._request(
        "POST", f"/{backend.config.alias_name}/_mget", {"ids": chunk_ids}
    )
    chunks: dict[str, dict[str, Any]] = {}
    for row in response.get("docs", []):
        if not row.get("found"):
            continue
        source = row.get("_source", {})
        chunk_id = str(source.get("chunk_id", row.get("_id", "")))
        chunks[chunk_id] = {
            "chunk_id": chunk_id,
            "document_id": str(source.get("doc_id", "")),
            "source_type": str(source.get("source_type", "unknown")),
            "text": str(source.get("text", "")),
        }
    missing = [chunk_id for chunk_id in chunk_ids if chunk_id not in chunks]
    if missing:
        raise ValueError(f"exact chunk lookup missed {len(missing)} IDs")
    return chunks


def bounded_candidates(
    ordered_chunks: list[dict[str, Any]], limit: int, per_document: int
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    document_counts: dict[str, int] = {}
    for chunk in ordered_chunks:
        doc_id = chunk["document_id"]
        if document_counts.get(doc_id, 0) >= per_document:
            continue
        selected.append(chunk)
        document_counts[doc_id] = document_counts.get(doc_id, 0) + 1
        if len(selected) >= limit:
            break
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--traces", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--question-id", action="append", required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.repetitions < 1:
        raise ValueError("repetitions must be positive")

    questions = load_jsonl(args.questions)
    traces = load_jsonl(args.traces)
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    generation = config["generation"]
    if generation.get("evidence_selection_mode") != "precision_v3":
        raise ValueError("config is not a precision_v3 selector run")

    backend = ElasticsearchBackend(ElasticsearchConfig(**config["elasticsearch"]))
    llm = create_llm_client(LLMConfig(**config["llm"]))
    candidate_limit = int(generation["evidence_selection_candidate_chunks"])
    max_chunks = int(generation["evidence_selection_max_chunks"])
    per_document = int(generation["max_chunks_per_doc"])

    reports: list[dict[str, Any]] = []
    for question_id in args.question_id:
        if question_id not in questions or question_id not in traces:
            raise ValueError(f"missing frozen question or trace for {question_id}")
        question = str(questions[question_id].get("question", ""))
        trace = traces[question_id]
        final_stage = trace.get("retrieval_stages", {}).get("final_before_generation", {})
        chunk_ids = [str(item) for item in final_stage.get("chunk_ids", []) if item]
        if not chunk_ids:
            raise ValueError(f"frozen trace has no final chunks for {question_id}")
        fetched = fetch_chunks(backend, chunk_ids)
        candidates = bounded_candidates(
            [fetched[chunk_id] for chunk_id in chunk_ids],
            candidate_limit,
            per_document,
        )
        documents = "\n\n".join(
            f"[{index}] (source: {chunk['source_type']}, doc_id: {chunk['document_id']})\n"
            f"{chunk['text']}"
            for index, chunk in enumerate(candidates, 1)
        )
        question_type = str(trace.get("inferred_question_type", ""))
        prompt = PRECISION_EVIDENCE_SELECTION_USER_TEMPLATE.format(
            question=question,
            documents=documents,
            max_chunks=max_chunks,
            mode_rules=Generator._question_type_rules(question_type),
        )
        attempts: list[dict[str, Any]] = []
        for repetition in range(1, args.repetitions + 1):
            response = llm.generate(
                prompt, PRECISION_EVIDENCE_SELECTION_SYSTEM_PROMPT
            ).strip()
            attempts.append({
                "repetition": repetition,
                "raw_response": response,
                "strict_result": parse_strict_precision(response, len(candidates)),
            })
        reports.append({
            "question_id": question_id,
            "question": question,
            "question_type": question_type,
            "route_action": trace.get("route_action"),
            "candidate_count": len(candidates),
            "candidates": [
                {
                    "index": index,
                    "chunk_id": chunk["chunk_id"],
                    "document_id": chunk["document_id"],
                    "source_type": chunk["source_type"],
                }
                for index, chunk in enumerate(candidates, 1)
            ],
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "prompt": prompt,
            "attempts": attempts,
        })

    payload = {
        "schema_version": 1,
        "scope": "offline precision-v3 selector replay; no answer generation",
        "question_count": len(reports),
        "repetitions": args.repetitions,
        "reports": reports,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = {
        report["question_id"]: [
            attempt["strict_result"]["status"] for attempt in report["attempts"]
        ]
        for report in reports
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
