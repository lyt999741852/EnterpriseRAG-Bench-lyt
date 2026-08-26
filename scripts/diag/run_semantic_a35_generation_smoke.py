"""Run generation/final-audit smoke on frozen PageIndex evidence.

This deliberately bypasses retrieval and reranking.  It isolates the A3.5
generation prompt guard from the transient shared-reranker failures while
reusing the exact final-before-generation chunk IDs from a completed AB50
route trace.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from src.elasticsearch_backend import ElasticsearchBackend, ElasticsearchConfig
from src.evaluator import load_questions
from src.generator import Generator, GeneratorConfig
from src.llm import LLMConfig
from src.retriever import RetrieveResult


def _find_node(nodes: list[dict], node_id: str) -> dict | None:
    for node in nodes:
        if str(node.get("node_id", "")) == node_id:
            return node
        children = node.get("nodes", [])
        if isinstance(children, list):
            found = _find_node(children, node_id)
            if found is not None:
                return found
    return None


def _flatten_text(nodes: list[dict]) -> str:
    parts: list[str] = []
    for node in nodes:
        text = node.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text)
        children = node.get("nodes", [])
        if isinstance(children, list):
            nested = _flatten_text(children)
            if nested:
                parts.append(nested)
    return "\n\n".join(parts)


def fetch_chunks(
    backend: ElasticsearchBackend, cache_dir: Path, chunk_ids: list[str]
) -> list[RetrieveResult]:
    """Load both ES fixed chunks and PageIndex node chunks by exact ID."""
    pageindex_ids = [chunk_id for chunk_id in chunk_ids if "__pageindex__" in chunk_id]
    es_ids = [chunk_id for chunk_id in chunk_ids if "__pageindex__" not in chunk_id]
    by_id: dict[str, RetrieveResult] = {}
    for chunk_id in pageindex_ids:
        doc_id, suffix = chunk_id.split("__pageindex__", 1)
        node_id = suffix.lstrip("_")
        matches = list(cache_dir.glob(f"{doc_id}-*.json"))
        if not matches:
            raise RuntimeError(f"missing PageIndex cache for {doc_id}")
        page = json.loads(matches[0].read_text(encoding="utf-8"))
        structure = page.get("structure", [])
        node = _find_node(structure, node_id)
        if node is None and node_id == "full":
            node = {"text": _flatten_text(structure)}
        if node is None:
            raise RuntimeError(f"missing PageIndex node {chunk_id}")
        by_id[chunk_id] = RetrieveResult(
            chunk_id=chunk_id,
            doc_id=doc_id,
            source_type=str(page.get("source_type", "pageindex")),
            text=str(node.get("text", "")),
            score=0.0,
        )
    if not es_ids:
        return [by_id[chunk_id] for chunk_id in chunk_ids]
    data = backend._request(
        "POST", f"/{backend.config.alias_name}/_mget", {"ids": es_ids}
    )
    for row in data.get("docs", []):
        if not row.get("found"):
            continue
        source = row.get("_source", {})
        chunk_id = str(source.get("chunk_id", row.get("_id", "")))
        by_id[chunk_id] = RetrieveResult(
            chunk_id=chunk_id,
            doc_id=str(source.get("doc_id", "")),
            source_type=str(source.get("source_type", "unknown")),
            text=str(source.get("text", "")),
            score=0.0,
        )
    missing = [chunk_id for chunk_id in es_ids if chunk_id not in by_id]
    if missing:
        raise RuntimeError(f"missing {len(missing)} frozen chunks")
    return [by_id[chunk_id] for chunk_id in chunk_ids]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--questions-file", type=Path, required=True)
    parser.add_argument("--route-trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    questions = load_questions(str(args.questions_file))
    traces = {
        row["question_id"]: row
        for row in (json.loads(line) for line in args.route_trace.read_text(encoding="utf-8").splitlines())
        if row.get("question_id")
    }
    qids = list(cfg["pipeline"].get("question_ids", []))
    missing = [qid for qid in qids if qid not in questions or qid not in traces]
    if missing:
        raise RuntimeError(f"missing question/trace rows: {missing}")

    backend = ElasticsearchBackend(ElasticsearchConfig(**cfg["elasticsearch"]))
    cache_dir = Path(cfg["pageindex"].get("cache_dir", ".pageindex_cache"))
    generation_cfg = cfg.get("generation", {})
    generator = Generator(
        GeneratorConfig(
            llm=LLMConfig(**cfg["llm"]),
            max_context_chunks=generation_cfg.get("max_context_chunks", 5),
            max_chunks_per_doc=generation_cfg.get("max_chunks_per_doc", 2),
            max_document_ids=generation_cfg.get("max_document_ids", 10),
            evidence_selection_enabled=False,
            fact_verification_enabled=generation_cfg.get("fact_verification_enabled", True),
            final_answer_audit_enabled=generation_cfg.get("final_answer_audit_enabled", True),
        )
    )

    rows: list[dict] = []
    for qid in qids:
        question = questions[qid]
        trace = traces[qid]
        frozen = trace["retrieval_stages"]["final_before_generation"]
        chunks = fetch_chunks(backend, cache_dir, list(frozen.get("chunk_ids", [])))
        question_text = str(question.get("question", question.get("query", "")))
        question_type = trace.get("inferred_question_type")
        answer = generator._generate_and_verify(question_text, chunks, question_type)
        answer, selected = generator._audit_final_answer_and_sources(
            question_text, chunks, answer, question_type
        )
        answer = generator._remove_unasked_follow_up_state(question_text, answer)
        answer = generator._repair_supported_coverage(question_text, selected, answer)
        answer = generator._normalize_typo_glyphs(answer)
        rows.append({
            "question_id": qid,
            "answer": answer,
            "document_ids": list(dict.fromkeys(item.doc_id for item in selected)),
        })
        print(f"{qid}: {answer[:180]}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(f"wrote {len(rows)} answers to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
