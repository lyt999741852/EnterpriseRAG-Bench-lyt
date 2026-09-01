"""Offline S1 test: generic semantic query views with append-only retrieval.

Views are generated only from the question text using generic role/action/time
slots. No answer, qid, expected document, or corpus-derived term is used.
The original dense/BM25 top-120 is preserved; view results are appended into a
bounded 500-item pool for an admission upper-bound measurement.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


STOP = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by",
    "can", "could", "did", "do", "does", "for", "from", "get", "got",
    "had", "has", "have", "how", "i", "if", "in", "into", "is", "it",
    "its", "may", "might", "more", "of", "on", "or", "our", "should",
    "that", "the", "their", "them", "there", "these", "this", "those",
    "to", "under", "was", "were", "what", "when", "where", "which", "who",
    "why", "will", "with", "would", "you", "your", "please", "following",
    "according", "during", "between", "each", "side", "具体", "具体的",
}
ROLE = {
    "vendor", "supplier", "customer", "partner", "isv", "client", "team",
    "owner", "approver", "lead", "manager", "author", "operator", "user",
    "buyer", "seller", "provider", "recipient", "sender", "participant",
    "participants", "department", "organization", "company", "person",
}
ACTION = {
    "send", "sent", "submit", "submitted", "deliver", "delivered", "provide",
    "provided", "share", "shared", "approve", "approved", "review", "reviewed",
    "schedule", "scheduled", "commit", "committed", "own", "owns", "负责",
    "deadline", "deadlines", "due", "date", "dates", "timeline", "timing",
    "responsibility", "responsibilities", "require", "requires", "identify",
    "identified", "compare", "compared", "decide", "decision", "plan", "planning",
}
TIME = {
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "q1", "q2", "q3", "q4",
    "year", "month", "week", "day", "today", "tomorrow", "late", "early",
    "mid", "before", "after", "within", "by", "deadline", "date", "dates",
}


def call_json(url: str, payload: dict) -> dict:
    req = Request(url, data=json.dumps(payload).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode())


def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    return {str(r["question_id"]): r for r in (json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()) if r.get("question_id")}


def source_doc(hit: dict[str, Any]) -> str:
    src = hit.get("_source") or {}
    return str(src.get("doc_id") or src.get("chunk_id") or hit.get("_id", "")).split("__", 1)[0]


def tokens(text: str) -> list[str]:
    return [x.lower() for x in re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}|\d{1,4}(?:/\d{1,2})?", text)]


def views(question: str) -> dict[str, str]:
    raw = tokens(question)
    content = [x for x in raw if x not in STOP]
    roles = [x for x in content if x in ROLE]
    actions = [x for x in content if x in ACTION]
    times = [x for x in content if x in TIME or re.fullmatch(r"\d{1,4}(?:/\d{1,2})?", x)]
    objects = [x for x in content if x not in set(roles + actions + times)]
    def uniq(xs: list[str]) -> list[str]:
        return list(dict.fromkeys(xs))
    return {
        "event": "event meeting call discussion " + " ".join(uniq(objects[:12])),
        "relation": "participants roles responsibilities actions " + " ".join(uniq(roles + actions)),
        "object_time": "objects deliverables timeline deadlines " + " ".join(uniq(objects + times)),
    }


def hit_stats(values: list[str], expected: set[str], cutoffs: tuple[int, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in cutoffs:
        found = set(values[:k]) & expected
        out[str(k)] = {"hit": bool(found), "expected_found": len(found), "expected_total": len(expected), "coverage_pct": round(100 * len(found) / len(expected), 2) if expected else None}
    out["first_expected_rank"] = next((i for i, v in enumerate(values, 1) if v in expected), None)
    return out


def union_hit_stats(lists: list[list[str]], expected: set[str], cutoffs: tuple[int, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in cutoffs:
        found = set().union(*(set(values[:k]) for values in lists)) & expected
        out[str(k)] = {"hit": bool(found), "expected_found": len(found), "expected_total": len(expected), "coverage_pct": round(100 * len(found) / len(expected), 2) if expected else None}
    ranks = [k for k in cutoffs if out[str(k)]["hit"]]
    out["first_expected_rank"] = ranks[0] if ranks else None
    return out


def rrf_fuse(lists: list[list[str]], weights: list[float], top_n: int, rrf_k: int = 60) -> list[str]:
    scores: dict[str, float] = {}
    for weight, values in zip(weights, lists):
        for rank, value in enumerate(values, 1):
            scores[value] = scores.get(value, 0.0) + float(weight) / (rrf_k + rank)
    return [value for value, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:top_n]]


def aggregate(rows: list[dict[str, Any]], key: str, cutoffs: tuple[int, ...]) -> dict[str, Any]:
    out = {"question_count": len(rows)}
    for k in cutoffs:
        vals = [r[key][str(k)]["hit"] for r in rows]
        cov = [r[key][str(k)]["coverage_pct"] for r in rows if r[key][str(k)]["coverage_pct"] is not None]
        out[f"hit_rate_at_{k}"] = round(100 * sum(vals) / len(vals), 2) if vals else None
        out[f"mean_coverage_at_{k}"] = round(sum(cov) / len(cov), 2) if cov else None
    ranks = [r[key]["first_expected_rank"] for r in rows if r[key]["first_expected_rank"] is not None]
    out["ranked_question_count"] = len(ranks)
    out["mean_first_expected_rank"] = round(sum(ranks) / len(ranks), 2) if ranks else None
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", type=Path, required=True)
    ap.add_argument("--o0-funnel", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--es", default="http://127.0.0.1:9200")
    ap.add_argument("--index", default="enterprise-rag-bge-small-v1")
    ap.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()
    questions = load_jsonl(args.questions)
    funnel = json.loads(args.o0_funnel.read_text(encoding="utf-8"))
    effective = [str(r["question_id"]) for r in funnel.get("rows", []) if r.get("expected_document_ids") and str(r.get("question_id")) in questions]
    semantic = [qid for qid in effective if questions[qid].get("question_type") == "semantic"]
    if not semantic:
        raise RuntimeError("no semantic questions")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(args.model, local_files_only=True)
    all_queries: list[str] = []
    query_by_qid: dict[str, dict[str, str]] = {}
    for qid in effective:
        q = str(questions[qid]["question"])
        qviews = views(q)
        query_by_qid[qid] = {"original": q, **qviews}
        all_queries.extend(query_by_qid[qid].values())
    vectors = model.encode(all_queries, normalize_embeddings=True, batch_size=32, show_progress_bar=False).tolist()
    offset = 0
    vectors_by_qid: dict[str, dict[str, list[float]]] = {}
    for qid in effective:
        names = list(query_by_qid[qid])
        vectors_by_qid[qid] = dict(zip(names, vectors[offset:offset + len(names)]))
        offset += len(names)
    cutoffs = (30, 120, 240, 500)

    def search(qid: str) -> dict[str, Any]:
        q = query_by_qid[qid]
        expected = {str(x) for x in questions[qid].get("expected_doc_ids", []) if x}
        dense_lists: dict[str, list[str]] = {}
        bm25_lists: dict[str, list[str]] = {}
        latency = 0.0
        for name, text in q.items():
            dense_body = {"size": 500, "knn": {"field": "embedding", "query_vector": vectors_by_qid[qid][name], "k": 500, "num_candidates": 1000}, "_source": ["doc_id", "chunk_id"]}
            bm25_body = {"size": 500, "query": {"match": {"text": {"query": text}}}, "_source": ["doc_id", "chunk_id"]}
            t = time.perf_counter(); dh = call_json(f"{args.es.rstrip('/')}/{args.index}/_search", dense_body).get("hits", {}).get("hits", []); latency += (time.perf_counter() - t) * 1000
            t = time.perf_counter(); bh = call_json(f"{args.es.rstrip('/')}/{args.index}/_search", bm25_body).get("hits", {}).get("hits", []); latency += (time.perf_counter() - t) * 1000
            dense_lists[name] = [source_doc(h) for h in dh]
            bm25_lists[name] = [source_doc(h) for h in bh]
        base = rrf_fuse([bm25_lists["original"], dense_lists["original"]], [1.2, 1.0], 120)
        append_pool = list(base)
        # Preserve the original retrieval tail before adding semantic views.
        # This keeps the production top-500 coverage as the no-regression floor.
        for name in ("original", "event", "relation", "object_time"):
            for arr in (bm25_lists[name], dense_lists[name]):
                for v in arr:
                    if v not in append_pool:
                        append_pool.append(v)
                        if len(append_pool) >= 500: break
                if len(append_pool) >= 500: break
            if len(append_pool) >= 500: break
        view_union: list[str] = []
        for name in q:
            for arr in (bm25_lists[name], dense_lists[name]):
                for v in arr:
                    if v not in view_union: view_union.append(v)
        return {"question_id": qid, "question_type": questions[qid].get("question_type"), "expected_document_ids": sorted(expected), "base": union_hit_stats([bm25_lists["original"], dense_lists["original"]], expected, cutoffs), "append_pool": hit_stats(append_pool, expected, cutoffs), "view_union": union_hit_stats([arr for name in q for arr in (bm25_lists[name], dense_lists[name])], expected, cutoffs), "views": q, "latency_ms": round(latency, 2)}

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(search, qid): qid for qid in effective}
        for i, fut in enumerate(as_completed(futures), 1):
            rows.append(fut.result())
            if i % 25 == 0 or i == len(effective): print(f"[{i}/{len(effective)}]", flush=True)
    rows.sort(key=lambda r: effective.index(r["question_id"]))
    semantic_set = set(semantic)
    groups = {"semantic": [r for r in rows if r["question_id"] in semantic_set], "controls": [r for r in rows if r["question_id"] not in semantic_set], "effective": rows}
    report = {"schema_version": 1, "scope": "S1 generic semantic views, original-only input, append-only top-500 offline probe", "index": args.index, "model": args.model, "effective_question_count": len(rows), "semantic_question_count": len(semantic), "cutoffs": list(cutoffs), "groups": {name: {"question_count": len(group), "base": aggregate(group, "base", cutoffs), "append_pool": aggregate(group, "append_pool", cutoffs), "view_union": aggregate(group, "view_union", cutoffs), "mean_latency_ms": round(statistics.mean(r["latency_ms"] for r in group), 2) if group else None} for name, group in groups.items()}, "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["groups"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
