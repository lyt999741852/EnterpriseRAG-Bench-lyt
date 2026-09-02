"""Read-only field-profile BM25 probe for the five raw-miss questions."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

STOP = {"what", "which", "where", "when", "does", "did", "have", "with", "from", "that", "this", "about", "into", "their", "there", "were", "been", "will", "would", "could", "should", "during", "between", "please", "according", "explain", "describe", "provide", "using"}


def post(base: str, path: str, body: dict) -> dict:
    req = Request(base.rstrip("/") + path, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode())


def anchors(question: str) -> list[str]:
    out = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_.:/-]{2,}", question):
        low = token.lower().strip("._:/-")
        if low in STOP or token in out:
            continue
        if any(ch.isdigit() for ch in token) or token.isupper() or len(token) >= 6:
            out.append(token)
    return out[:20]


def doc_id(hit: dict) -> str:
    source = hit.get("_source") or {}
    return str(source.get("doc_id") or source.get("chunk_id", "").split("__", 1)[0])


def rank(hits: list[dict], expected: set[str]) -> int | None:
    for n, hit in enumerate(hits, 1):
        if doc_id(hit) in expected:
            return n
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--es-url", default=os.environ.get("ES_URL", "http://127.0.0.1:9200"))
    ap.add_argument("--index", default=os.environ.get("ES_INDEX", "enterprise-rag-bge-small-v1"))
    ap.add_argument("--top-k", type=int, default=1000)
    args = ap.parse_args()
    questions = {}
    for line in Path(args.questions).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("question_id"):
            questions[row["question_id"]] = row
    profiles = {
        "title_text_balanced": {"multi_match": {"query": "{q}", "fields": ["title^2", "text"], "type": "best_fields"}},
        "title_heavy": {"multi_match": {"query": "{q}", "fields": ["title^8", "text"], "type": "best_fields"}},
        "cross_fields": {"multi_match": {"query": "{q}", "fields": ["title^2", "text"], "type": "cross_fields", "operator": "and"}},
        "phrase_or_terms": {"bool": {"should": [{"match_phrase": {"title": {"query": "{q}", "boost": 8}}}, {"simple_query_string": {"query": "{a}", "fields": ["title^4", "text"]}}], "minimum_should_match": 1}},
    }
    qids = ["qst_0116", "qst_0184", "qst_0231", "qst_0251", "qst_0298"]
    rows = []
    for qid in qids:
        question = str(questions[qid]["question"])
        expected = {str(x) for x in questions[qid].get("expected_doc_ids", []) if x}
        anchor_text = " ".join(anchors(question)) or question
        profile_rows = {}
        for name, query in profiles.items():
            encoded = json.loads(json.dumps(query).replace("{q}", question).replace("{a}", anchor_text))
            hits = post(f"{args.es_url}/{args.index}", "/_search", {"size": args.top_k, "_source": ["doc_id", "chunk_id", "title", "file_path", "source_type"], "query": encoded}).get("hits", {}).get("hits", [])
            profile_rows[name] = {"target_rank": rank(hits, expected), "top_score": hits[0].get("_score") if hits else None, "tail_score": hits[-1].get("_score") if hits else None, "target_scores": [h.get("_score") for h in hits if doc_id(h) in expected], "target_documents": sorted({doc_id(h) for h in hits if doc_id(h) in expected})}
        rows.append({"question_id": qid, "anchor_tokens": anchors(question), "profiles": profile_rows})
    summary = {name: sum(row["profiles"][name]["target_rank"] is not None for row in rows) for name in profiles}
    output = {"schema_version": 1, "scope": "R11.E read-only field-profile BM25 probe", "index": args.index, "top_k": args.top_k, "summary": summary, "rows": rows}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
