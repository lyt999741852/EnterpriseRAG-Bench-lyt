"""Probe lexical anchor variants for raw-miss questions (read-only)."""

from __future__ import annotations

import argparse
import itertools
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen


STOP = {
    "what", "which", "where", "when", "does", "did", "have", "with",
    "from", "that", "this", "about", "into", "their", "there", "were",
    "been", "will", "would", "could", "should", "during", "between",
    "please", "according", "explain", "describe", "provide", "using",
}


def call_json(base: str, path: str, payload: dict) -> dict:
    req = Request(
        base.rstrip("/") + path,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode())


def anchors(question: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_.:/-]{2,}", question)
    result: list[str] = []
    for token in tokens:
        low = token.lower().strip("._:/-")
        if low in STOP or token in result:
            continue
        if any(ch.isdigit() for ch in token) or token.isupper() or len(token) >= 6:
            result.append(token)
    return result[:20]


def rank_target(hits: list[dict], expected: set[str]) -> tuple[int | None, float | None]:
    for rank, hit in enumerate(hits, 1):
        source = hit.get("_source") or {}
        if source.get("doc_id") in expected:
            return rank, hit.get("_score")
        chunk_id = source.get("chunk_id", hit.get("_id", ""))
        if any(chunk_id.startswith(doc + "__") for doc in expected):
            return rank, hit.get("_score")
    return None, None


def search(es: str, index: str, query: dict, size: int = 200) -> tuple[list[dict], float | None]:
    body = {
        "size": size,
        "_source": ["doc_id", "chunk_id"],
        "query": query,
    }
    data = call_json(f"{es}/{index}", "/_search", body)
    hits = data.get("hits", {}).get("hits", [])
    return hits, min((h.get("_score") for h in hits if h.get("_score") is not None), default=None)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", default="questions.jsonl")
    parser.add_argument(
        "--failure-layers",
        default="outputs/pageindex_ab50_semantic_conflict_guard_r3_20260826/retrieval_failure_layers.json",
    )
    parser.add_argument("--output", default="outputs/raw_miss_lexical_anchor_variants.json")
    parser.add_argument("--es-url", default="http://127.0.0.1:9200")
    parser.add_argument("--index", default="enterprise-rag-bge-small-v1")
    args = parser.parse_args()

    questions = {
        row["question_id"]: row
        for row in (json.loads(x) for x in Path(args.questions).read_text(encoding="utf-8").splitlines())
    }
    failures = json.loads(Path(args.failure_layers).read_text(encoding="utf-8"))
    raw = [row for row in failures["rows"] if row.get("bucket") == "raw_miss"]
    rows = []
    for failure in raw:
        qid = failure["question_id"]
        question = questions[qid]["question"]
        expected = set(failure.get("expected_document_ids") or [])
        toks = anchors(question)
        variants: list[dict] = []

        def run(label: str, query: dict) -> None:
            hits, boundary = search(args.es_url, args.index, query)
            rank, score = rank_target(hits, expected)
            variants.append({"label": label, "query": query, "target_rank": rank, "target_score": score, "top200_boundary": boundary})

        run("question_or", {"multi_match": {"query": question, "fields": ["title^2", "text"], "operator": "or"}})
        run("question_and", {"multi_match": {"query": question, "fields": ["title^2", "text"], "operator": "and"}})
        for token in toks:
            run(f"token:{token}", {"multi_match": {"query": token, "fields": ["title^2", "text"], "operator": "and"}})
        # Test short, question-derived combinations without using gold text.
        for left, right in itertools.combinations(toks[:10], 2):
            query = f"{left} {right}"
            run(f"pair:{left}+{right}", {"simple_query_string": {"query": query, "fields": ["title^2", "text"]}})

        hits = [v for v in variants if v["target_rank"] is not None]
        best = sorted(hits, key=lambda v: (v["target_rank"], -(v["target_score"] or 0)))[:5]
        rows.append(
            {
                "question_id": qid,
                "question": question,
                "expected_document_ids": sorted(expected),
                "anchor_tokens": toks,
                "variant_count": len(variants),
                "target_reached_top200": bool(hits),
                "best_target_variants": best,
                "target_reached_variants": [v["label"] for v in hits],
            }
        )

    output = {
        "schema_version": 1,
        "index": args.index,
        "raw_miss_count": len(rows),
        "target_reached_top200_count": sum(row["target_reached_top200"] for row in rows),
        "rows": rows,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"raw_miss_count": len(rows), "target_reached_top200_count": output["target_reached_top200_count"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
