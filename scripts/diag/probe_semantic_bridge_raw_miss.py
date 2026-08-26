"""Offline A1 probe for a question-grounded Semantic bridge retrieval query.

The probe uses gold document IDs only after retrieval, to measure whether the
bridge query can recover documents that every S1 raw retrieval view missed. It
never sends those IDs, benchmark labels, or answers to the query planner.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from src.elasticsearch_backend import ElasticsearchBackend, ElasticsearchConfig, ElasticsearchRetriever
from src.embedder import EmbedderConfig, create_embedder
from src.llm import LLMConfig, create_llm_client


SYSTEM_PROMPT = (
    "You create one conservative enterprise retrieval query. Return only the "
    "query, without a label, answer, explanation, or facts not stated in the "
    "question."
)


def bridge_query(question: str, llm: Any) -> str:
    prompt = f"""Rewrite this enterprise search question as exactly one natural-language
semantic retrieval query. Keep every named entity, product/system name, event,
time/causal relationship, qualifier, version, date, number and unit that is
explicitly present. Emphasize the relationship between those stated elements
as it could appear in an authoritative source passage.

Do not answer the question. Do not infer an unstated person, value, outcome,
synonym, document name, or conclusion. Do not use benchmark labels or metadata.

Question: {question}

Bridge retrieval query:"""
    response = llm.generate(prompt, system_prompt=SYSTEM_PROMPT).strip()
    if response.startswith("[LLM_ERROR:"):
        raise RuntimeError(response)
    value = response.splitlines()[0].strip().lstrip("-*0123456789. ").strip()
    if len(value) < 4:
        raise ValueError("bridge planner returned an empty query")
    return value


def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            result[str(row["question_id"])] = row
    return result


def first_document_rank(results: list[Any], expected_docs: set[str]) -> int | None:
    seen: set[str] = set()
    for result in results:
        if result.doc_id in seen:
            continue
        seen.add(result.doc_id)
        if result.doc_id in expected_docs:
            return len(seen)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--failure-layers", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    failures = json.loads(args.failure_layers.read_text(encoding="utf-8"))
    raw_misses = [
        row for row in failures.get("rows", [])
        if row.get("bucket") == "raw_miss"
    ]
    if not raw_misses:
        raise ValueError("failure report has no raw_miss rows")
    questions = load_jsonl(args.questions)

    embedding = create_embedder(EmbedderConfig(**config["embedding"]))
    backend = ElasticsearchBackend(ElasticsearchConfig(**config["elasticsearch"]))
    retrieval = config["retrieval"]
    reranker = retrieval.get("reranker", {})
    top_k = int(reranker.get("candidate_k", retrieval.get("top_k", 30)))
    retriever = ElasticsearchRetriever(
        backend,
        embedding,
        top_k=top_k,
        candidate_k=int(retrieval.get("candidate_k", top_k)),
        rrf_k=int(retrieval.get("rrf_k", 60)),
        query_prefix=config.get("embedding", {}).get("query_prefix", ""),
    )
    llm = create_llm_client(LLMConfig(**config["llm"]))

    rows: list[dict[str, Any]] = []
    for failure in raw_misses:
        question_id = str(failure["question_id"])
        question = questions.get(question_id)
        if not question:
            raise ValueError(f"question missing from questions file: {question_id}")
        query = bridge_query(str(question["question"]), llm)
        results = retriever.retrieve_dense(query)
        rank = first_document_rank(
            results, {str(value) for value in failure["expected_document_ids"]}
        )
        rows.append({
            "question_id": question_id,
            "bridge_query": query,
            "bridge_document_hit": rank is not None,
            "first_matching_document_rank": rank,
            "retrieved_document_count": len({item.doc_id for item in results}),
        })

    hits = sum(1 for row in rows if row["bridge_document_hit"])
    report = {
        "schema_version": 1,
        "scope": "offline raw-miss probe; gold is used only after retrieval",
        "source_config": str(args.config),
        "raw_miss_question_count": len(rows),
        "bridge_document_hits": hits,
        "bridge_document_hit_pct": round(100 * hits / len(rows), 2),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in report if key != "rows"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
