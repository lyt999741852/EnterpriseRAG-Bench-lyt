"""Read-only audit of raw-miss questions against the live BGE ES index.

The audit does not write to Elasticsearch or alter the retrieval pipeline.  It
checks three independent explanations for a raw miss: target chunks absent
from the index, target chunks present but not reached by dense retrieval, and
lexical-anchor mismatch between the question and the indexed target text.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen


STOP = {
    "what", "which", "where", "when", "does", "did", "have", "with",
    "from", "that", "this", "about", "into", "their", "there", "were",
    "been", "will", "would", "could", "should", "during", "between",
    "please", "according", "explain", "describe", "provide", "using",
}


def call_json(base: str, path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(
        base.rstrip("/") + path,
        data=data,
        method="POST" if payload is not None else "GET",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode())


def anchors(question: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_.:/-]{2,}", question)
    out: list[str] = []
    for token in tokens:
        low = token.lower().strip("._:/-")
        if low in STOP or token in out:
            continue
        # Keep product names, identifiers, versions, numbers and long nouns.
        if any(ch.isdigit() for ch in token) or token.isupper() or len(token) >= 6:
            out.append(token)
    return out[:20]


def target_rank(hits: list[dict], expected: set[str]) -> int | None:
    for rank, hit in enumerate(hits, 1):
        source = hit.get("_source") or {}
        if source.get("doc_id") in expected:
            return rank
        chunk_id = source.get("chunk_id", hit.get("_id", ""))
        if any(chunk_id.startswith(doc + "__") for doc in expected):
            return rank
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", default="questions.jsonl")
    parser.add_argument(
        "--failure-layers",
        default="outputs/pageindex_ab50_semantic_conflict_guard_r3_20260826/retrieval_failure_layers.json",
    )
    parser.add_argument(
        "--route-trace",
        default="outputs/pageindex_ab50_semantic_conflict_guard_r3_20260826/route_trace.jsonl",
    )
    parser.add_argument("--output", default="outputs/raw_miss_embedding_lexical_audit.json")
    parser.add_argument("--es-url", default=os.environ.get("ES_URL", "http://127.0.0.1:9200"))
    parser.add_argument(
        "--index",
        default=os.environ.get("ES_INDEX", "enterprise-rag-bge-small-v1"),
    )
    parser.add_argument(
        "--embedding-url",
        default=os.environ.get("EMBEDDING_URL", "http://10.72.55.209:7993/v1/embeddings"),
    )
    parser.add_argument("--local-model", default=os.environ.get("LOCAL_EMBEDDING_MODEL", ""))
    args = parser.parse_args()

    questions = {
        row["question_id"]: row
        for row in (json.loads(line) for line in Path(args.questions).read_text(encoding="utf-8").splitlines())
        if row.get("question_id")
    }
    failures = json.loads(Path(args.failure_layers).read_text(encoding="utf-8"))
    raw_rows = [row for row in failures["rows"] if row.get("bucket") == "raw_miss"]
    traces = {
        row["question_id"]: row
        for row in (json.loads(line) for line in Path(args.route_trace).read_text(encoding="utf-8").splitlines())
    }

    mapping = call_json(f"{args.es_url}/{args.index}", "/_mapping")
    index_properties = mapping[args.index]["mappings"]["properties"]
    index_embedding_dims = index_properties.get("embedding", {}).get("dims")
    embedding_api_dimension: int | None = None
    embedding_dimension_error: str | None = None
    local_model = None
    local_model_error: str | None = None
    if args.local_model:
        try:
            from sentence_transformers import SentenceTransformer

            local_model = SentenceTransformer(args.local_model, local_files_only=True)
        except Exception as exc:  # keep the API probe as a fallback
            local_model_error = f"{type(exc).__name__}: {exc}"

    report_rows: list[dict] = []
    for failure in raw_rows:
        qid = failure["question_id"]
        question = questions[qid]["question"]
        expected = set(failure.get("expected_document_ids") or [])
        trace = traces.get(qid, {})
        views = (trace.get("retrieval_stages") or {}).get("views") or []
        raw_chunks = [chunk for view in views for chunk in view.get("chunk_ids", [])]
        raw_target_ranks = [
            i for i, chunk in enumerate(raw_chunks, 1)
            if any(chunk.startswith(doc + "__") for doc in expected)
        ]

        count_body = {"query": {"terms": {"doc_id": sorted(expected)}}}
        count = call_json(f"{args.es_url}/{args.index}", "/_count", count_body).get("count", 0)
        target_body = {
            "size": 200,
            "_source": ["doc_id", "chunk_id", "text", "title", "embedding_model", "file_path", "embedding"],
            "query": {"terms": {"doc_id": sorted(expected)}},
            "sort": ["chunk_index"],
        }
        target_hits = call_json(f"{args.es_url}/{args.index}", "/_search", target_body).get("hits", {}).get("hits", [])
        target_text = " ".join(
            str((hit.get("_source") or {}).get("text", ""))
            for hit in target_hits
        ).lower()
        anchor_tokens = anchors(question)
        anchor_hits = [token for token in anchor_tokens if token.lower() in target_text]

        lexical_body = {
            "size": 200,
            "_source": ["doc_id", "chunk_id"],
            "query": {"multi_match": {"query": question, "fields": ["title^2", "text"]}},
        }
        lexical_hits = call_json(f"{args.es_url}/{args.index}", "/_search", lexical_body).get("hits", {}).get("hits", [])
        anchor_query = " ".join(anchor_tokens) or question
        anchor_body = {
            "size": 200,
            "_source": ["doc_id", "chunk_id"],
            "query": {"simple_query_string": {"query": anchor_query, "fields": ["title^2", "text"]}},
        }
        anchor_hits_es = call_json(f"{args.es_url}/{args.index}", "/_search", anchor_body).get("hits", {}).get("hits", [])

        dense_hits: list[dict] = []
        probe_vector: list[float] | None = None
        try:
            if local_model is not None:
                vector = local_model.encode(question, normalize_embeddings=True).tolist()
                embedding_api_dimension = len(vector)
            else:
                embedding_req = Request(
                    args.embedding_url,
                    data=json.dumps({"model": "embedding", "input": [question], "encoding_format": "float"}).encode(),
                    method="POST",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {os.environ.get('EMBEDDING_API_KEY', '123456')}",
                    },
                )
                with urlopen(embedding_req, timeout=120) as response:
                    vector = json.loads(response.read().decode())["data"][0]["embedding"]
                embedding_api_dimension = len(vector)
            if index_embedding_dims != embedding_api_dimension:
                embedding_dimension_error = (
                    f"index_dims={index_embedding_dims}, probe_dims={embedding_api_dimension}"
                )
            else:
                probe_vector = vector
                dense_body = {
                    "knn": {"field": "embedding", "query_vector": vector, "k": 200, "num_candidates": 400},
                    "_source": ["doc_id", "chunk_id"],
                }
                dense_hits = call_json(f"{args.es_url}/{args.index}", "/_search", dense_body).get("hits", {}).get("hits", [])
        except Exception as exc:  # diagnostic should retain BM25/index evidence
            embedding_dimension_error = f"{type(exc).__name__}: {exc}"

        target_dense_scores = []
        if probe_vector is not None:
            # The target vectors are read only for these few documents; this
            # gives a score even when a target is below the ES top-200 cut.
            target_dense_scores = sorted(
                sum(a * b for a, b in zip(probe_vector, (hit.get("_source") or {}).get("embedding", [])))
                for hit in target_hits
                if len((hit.get("_source") or {}).get("embedding", [])) == len(probe_vector)
            )[::-1]
        if count == 0:
            diagnosis = "index_absent"
        elif embedding_dimension_error and "probe_dims=" in embedding_dimension_error:
            diagnosis = "embedding_dimension_mismatch_probe_unavailable"
        elif target_rank(dense_hits, expected) is None and target_rank(lexical_hits, expected) is None:
            diagnosis = "indexed_but_outside_dense_and_bm25_top200"
        elif len(anchor_hits) < max(1, min(2, len(anchor_tokens))):
            diagnosis = "lexical_anchor_gap"
        else:
            diagnosis = "indexed_and_retrievable_but_previous_route_miss"

        report_rows.append(
            {
                "question_id": qid,
                "question": question,
                "expected_document_ids": sorted(expected),
                "diagnosis": diagnosis,
                "index_target_chunk_count": count,
                "index_embedding_dims": index_embedding_dims,
                "embedding_api_dimension": embedding_api_dimension,
                "embedding_dimension_error": embedding_dimension_error,
                "local_model": args.local_model or None,
                "local_model_error": local_model_error,
                "target_embedding_models": sorted(
                    {(hit.get("_source") or {}).get("embedding_model") for hit in target_hits if (hit.get("_source") or {}).get("embedding_model")}
                ),
                "raw_trace_target_ranks": raw_target_ranks,
                "anchor_tokens": anchor_tokens,
                "target_text_anchor_hits": anchor_hits,
                "bm25_question_target_rank": target_rank(lexical_hits, expected),
                "bm25_anchor_target_rank": target_rank(anchor_hits_es, expected),
                "dense_target_rank": target_rank(dense_hits, expected),
                "dense_target_score": next(
                    (hit.get("_score") for hit in dense_hits if target_rank([hit], expected) == 1),
                    None,
                ),
                "target_dense_scores": target_dense_scores,
                "dense_top200_min_score": min(
                    (hit.get("_score") for hit in dense_hits if hit.get("_score") is not None),
                    default=None,
                ),
            }
        )

    summary = {}
    for row in report_rows:
        summary[row["diagnosis"]] = summary.get(row["diagnosis"], 0) + 1
    output = {
        "schema_version": 1,
        "index": args.index,
        "index_embedding_dims": index_embedding_dims,
        "embedding_api_dimension": embedding_api_dimension,
        "embedding_dimension_error": embedding_dimension_error,
        "local_model": args.local_model or None,
        "local_model_error": local_model_error,
        "embedding_endpoint": args.embedding_url,
        "raw_miss_count": len(report_rows),
        "diagnosis_counts": summary,
        "rows": report_rows,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"raw_miss_count": len(report_rows), "diagnosis_counts": summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
