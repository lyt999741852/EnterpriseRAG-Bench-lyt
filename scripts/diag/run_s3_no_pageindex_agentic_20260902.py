"""S3: fixed four-lane hybrid retrieval with optional coverage reflection.

This standalone runner deliberately bypasses PageIndex and question-type
routing.  It keeps the original lane, appends three deterministic views, and
optionally performs up to N LLM coverage/reflection rounds before generation.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

sys_path_root = str(Path(__file__).resolve().parents[2])
import sys
if sys_path_root not in sys.path:
    sys.path.insert(0, sys_path_root)

from src.elasticsearch_backend import ElasticsearchBackend, ElasticsearchConfig, ElasticsearchRetriever
from src.embedder import EmbedderConfig, create_embedder
from src.generator import Generator, GeneratorConfig
from src.llm import LLMConfig, OpenAICompatibleClient


STOP = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by",
    "can", "could", "did", "do", "does", "for", "from", "get", "got",
    "had", "has", "have", "how", "i", "if", "in", "into", "is", "it",
    "its", "may", "might", "more", "of", "on", "or", "our", "should",
    "that", "the", "their", "them", "there", "these", "this", "those", "to",
    "under", "was", "were", "what", "when", "where", "which", "who", "why",
    "will", "with", "would", "you", "your", "please", "following", "according",
}


def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row["question_id"]): row for row in (
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    )}


def tokenize(text: str) -> list[str]:
    return [x.lower() for x in re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}|\d{1,4}(?:/\d{1,2})?", text)]


def views(question: str) -> dict[str, str]:
    raw = tokenize(question)
    content = [x for x in raw if x not in STOP]
    uniq = lambda xs: list(dict.fromkeys(xs))
    lexical = " ".join(uniq(content))
    semantic = "event meeting discussion topic scenario facts " + " ".join(uniq(content[:24]))
    facet = "evidence answer facets entities dates quantities responsibilities outcomes " + " ".join(uniq(content))
    return {"original": question, "lexical": lexical, "semantic": semantic, "facet": facet}


def rrf_merge(groups: list[tuple[list[Any], float]], top_n: int, rrf_k: int = 60) -> list[Any]:
    scores: dict[str, float] = {}
    representative: dict[str, Any] = {}
    for values, weight in groups:
        for rank, item in enumerate(values, 1):
            key = item.chunk_id
            scores[key] = scores.get(key, 0.0) + float(weight) / (rrf_k + rank)
            representative.setdefault(key, item)
    return [representative[key] for key in sorted(scores, key=lambda k: (-scores[k], k))[:top_n]]


def doc_recall(values: list[Any], expected: set[str], cutoffs: tuple[int, ...]) -> dict[str, Any]:
    docs: list[str] = []
    seen: set[str] = set()
    for item in values:
        if item.doc_id and item.doc_id not in seen:
            seen.add(item.doc_id); docs.append(item.doc_id)
    out = {}
    for cutoff in cutoffs:
        found = set(docs[:cutoff]) & expected
        out[str(cutoff)] = {"hit": bool(found), "expected_found": len(found), "expected_total": len(expected), "coverage_pct": round(100 * len(found) / len(expected), 2) if expected else None}
    out["first_expected_rank"] = next((i for i, value in enumerate(docs, 1) if value in expected), None)
    return out


def aggregate(rows: list[dict[str, Any]], key: str, cutoffs: tuple[int, ...]) -> dict[str, Any]:
    return {
        "question_count": len(rows),
        **{f"hit_rate_at_{k}": round(100 * sum(r[key][str(k)]["hit"] for r in rows) / len(rows), 2) if rows else None for k in cutoffs},
        "ranked_question_count": sum(r[key]["first_expected_rank"] is not None for r in rows),
    }


def parse_json(text: str) -> dict[str, Any] | None:
    if not text or text.startswith("[LLM_ERROR:"):
        return None
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def coverage_prompt(question: str, chunks: list[Any]) -> str:
    docs = "\n\n".join(
        f"[{i}] doc_id={item.doc_id}\n{re.sub(r'\\s+', ' ', item.text)[:1800]}"
        for i, item in enumerate(chunks, 1)
    )
    return f"""Check evidence coverage for the question below. Do not answer it.
Return JSON only with keys sufficient (boolean), facets (array of objects with id, need,
covered, evidence_indices), missing_facets (array of strings), conflicts (array of strings),
and next_queries (array of at most 2 retrieval queries). Preserve every exact entity,
number, date, version, region, and qualifier from the question. A facet is covered only
when a supplied passage directly supports it; do not infer missing facts from memory.

Question: {question}

Candidate passages:
{docs}
"""


def make_generator() -> Generator:
    cfg = GeneratorConfig(
        llm=LLMConfig(provider="openai_compatible", api_base=os.environ.get("S3_DPV4_BASE", "http://10.72.100.29:18380/v1"), api_key_env="DPV4_API_KEY", model_name="deepseek-v4-flash", temperature=0.0, max_tokens=8192, timeout=180, retry_attempts=3, retry_backoff_seconds=1.0, extra_body={"chat_template_kwargs": {"enable_thinking": False}}),
        max_context_chunks=10, max_chunks_per_doc=4, max_document_ids=10,
        evidence_selection_enabled=True, evidence_selection_candidate_chunks=30,
        evidence_selection_max_chunks=10, evidence_selection_mode="precision_v3",
        evidence_selection_anchor_chunks=2, evidence_selection_fallback_chunks=4,
        evidence_selection_fail_closed=False, fact_verification_enabled=True,
        final_answer_audit_enabled=True,
    )
    return Generator(cfg)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", type=Path, required=True)
    ap.add_argument("--ids-file", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--answers", type=Path)
    ap.add_argument("--rounds", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--es", default="http://127.0.0.1:9200")
    ap.add_argument("--index", default="enterprise-rag-bge-small-v1")
    ap.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    ap.add_argument("--rerank-base", default="http://10.72.55.209:7992/v1")
    args = ap.parse_args()
    all_questions = load_jsonl(args.questions)
    qids = [x.strip() for x in args.ids_file.read_text(encoding="utf-8").splitlines() if x.strip()]
    questions = {qid: all_questions[qid] for qid in qids}
    if len(questions) != len(qids):
        raise ValueError("question id missing from questions.jsonl")
    embedder = create_embedder(EmbedderConfig(provider="sentence_transformers", model_name=args.model, device="cpu", batch_size=64, dimension=384, revision="5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"))
    backend = ElasticsearchBackend(ElasticsearchConfig(url=args.es, index_name=args.index, alias_name="enterprise-rag-bge-small", request_timeout=180))
    retriever = ElasticsearchRetriever(backend, embedder, top_k=120, candidate_k=500, rrf_k=60)
    embed_lock = threading.Lock()
    rerank_lock = threading.Lock()
    checker_cfg = LLMConfig(provider="openai_compatible", api_base=os.environ.get("S3_DPV4_BASE", "http://10.72.100.29:18380/v1"), api_key_env="DPV4_API_KEY", model_name="deepseek-v4-flash", temperature=0.0, max_tokens=2500, timeout=180, retry_attempts=2, retry_backoff_seconds=1.0, extra_body={"chat_template_kwargs": {"enable_thinking": False}})
    cutoffs = (30, 120, 240, 500)

    def retrieve(text: str) -> list[Any]:
        with embed_lock:
            return retriever.retrieve_hybrid(text, dense_weight=0.3)

    def one(qid: str) -> dict[str, Any]:
        q = questions[qid]; question = str(q["question"]); expected = {str(x) for x in q.get("expected_doc_ids", []) if x}; started = time.perf_counter(); lane_text = views(question)
        lane_results = {name: retrieve(text) for name, text in lane_text.items()}
        initial = rrf_merge([(lane_results[name], weight) for name, weight in (("original", 1.2), ("lexical", 1.0), ("semantic", 0.9), ("facet", 0.4))], 240)
        base = list(initial[:120]); candidate_pool = list(initial); reflection: list[dict[str, Any]] = []; checked = list(base); queries_seen: set[str] = set(); checker = OpenAICompatibleClient(checker_cfg) if args.rounds > 0 else None
        if checker is not None and checked:
            with rerank_lock:
                checked = retriever.rerank(question, checked, model_name="rerank", top_n=min(30, len(checked)), api_base=args.rerank_base, api_key_env="EMBEDDING_API_KEY", timeout=120)
        for round_index in range(0, max(0, min(args.rounds, 3)) + 1):
            if round_index == 0:
                pass
            else:
                prev = reflection[-1] if reflection else {}
                next_queries = [str(x).strip() for x in prev.get("next_queries", []) if str(x).strip()][:2]
                next_queries = [x for x in next_queries if x.lower() not in queries_seen]
                if not next_queries:
                    break
                new_items: list[Any] = []
                for next_query in next_queries:
                    queries_seen.add(next_query.lower()); new_items.extend(retrieve(next_query))
                seen = {x.chunk_id for x in candidate_pool}; appended = [x for x in new_items if x.chunk_id not in seen][:40]; candidate_pool.extend(appended)
                rerank_input = (checked + appended)[:120]
                if rerank_input:
                    with rerank_lock:
                        checked = retriever.rerank(question, rerank_input, model_name="rerank", top_n=min(30, len(rerank_input)), api_base=args.rerank_base, api_key_env="EMBEDDING_API_KEY", timeout=120)
            if checker is not None:
                response = checker.generate(coverage_prompt(question, checked[:20]), "You are a high-recall evidence coverage checker. Return JSON only.")
                value = parse_json(response) or {"sufficient": False, "facets": [], "missing_facets": [], "conflicts": [], "next_queries": []}
                value["round"] = round_index; reflection.append(value)
                if value.get("sufficient") is True:
                    break
        if args.rounds > 0 and not checked:
            checked = base
        answer_item = None
        if args.answers is not None:
            generator = make_generator()
            answer, docs = generator.generate_with_sources(question, checked[:120], None)
            answer_item = {"question_id": qid, "answer": answer, "document_ids": docs}
        return {"question_id": qid, "question_type": q.get("question_type"), "expected_document_ids": sorted(expected), "base": doc_recall(base, expected, cutoffs), "four_lane_pool": doc_recall(candidate_pool[:240], expected, cutoffs), "final_candidates": doc_recall(checked, expected, cutoffs), "lane_counts": {name: len(values) for name, values in lane_results.items()}, "reflection": reflection, "reflection_rounds": len(reflection), "answer": answer_item, "latency_ms": round((time.perf_counter() - started) * 1000, 2)}

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(one, qid): qid for qid in qids}
        for i, future in enumerate(as_completed(futures), 1):
            rows.append(future.result()); print(f"[{i}/{len(qids)}]", flush=True)
    rows.sort(key=lambda x: qids.index(x["question_id"]))
    groups = {"all": rows, "semantic": [r for r in rows if r["question_type"] == "semantic"], "controls": [r for r in rows if r["question_type"] != "semantic"]}
    report = {"schema_version": 1, "scope": "S3 fixed four-lane hybrid retrieval without PageIndex", "rounds": max(0, min(args.rounds, 3)), "question_count": len(rows), "cutoffs": list(cutoffs), "groups": {name: {"question_count": len(group), "base": aggregate(group, "base", cutoffs), "four_lane_pool": aggregate(group, "four_lane_pool", cutoffs), "final_candidates": aggregate(group, "final_candidates", cutoffs), "mean_reflection_rounds": round(statistics.mean(r["reflection_rounds"] for r in group), 2) if group else 0.0, "mean_latency_ms": round(statistics.mean(r["latency_ms"] for r in group), 2) if group else 0.0} for name, group in groups.items()}, "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.answers is not None:
        args.answers.parent.mkdir(parents=True, exist_ok=True); args.answers.write_text("\n".join(json.dumps(r["answer"], ensure_ascii=False) for r in rows if r.get("answer")) + "\n", encoding="utf-8")
    print(json.dumps(report["groups"], ensure_ascii=False)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
