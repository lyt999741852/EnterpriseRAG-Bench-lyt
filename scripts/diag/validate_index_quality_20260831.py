"""Read-only quality validation for BGE-small and Conan ES indices.

The audit is intentionally limited to the 46 effective O0 raw-miss questions.
It validates mapping, target-document/chunk coverage, text/chunk metadata, and
sampled vector dimensions/norms.  It never writes to Elasticsearch.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from urllib.request import Request, urlopen


def request_json(url: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(
        url,
        data=data,
        method="POST" if payload is not None else "GET",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode())


def load_jsonl(path: Path) -> dict[str, dict]:
    return {
        str(row["question_id"]): row
        for row in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
        if row.get("question_id")
    }


def percentile(values: list[int | float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def profile_chunks(hits: list[dict], expected: set[str]) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    lengths: list[int] = []
    empty_text = 0
    missing_title = 0
    for hit in hits:
        source = hit.get("_source") or {}
        doc_id = str(source.get("doc_id") or "")
        if doc_id not in expected:
            continue
        grouped[doc_id].append(source)
        text = str(source.get("text") or "")
        lengths.append(len(text))
        empty_text += not bool(text.strip())
        missing_title += not bool(str(source.get("title") or "").strip())
    gap_docs = 0
    single_chunk_docs = 0
    for rows in grouped.values():
        indices = sorted(
            int(row["chunk_index"])
            for row in rows
            if row.get("chunk_index") is not None
        )
        if len(rows) == 1:
            single_chunk_docs += 1
        if indices and indices != list(range(indices[0], indices[-1] + 1)):
            gap_docs += 1
    return {
        "target_doc_count": len(grouped),
        "target_chunk_count": sum(len(rows) for rows in grouped.values()),
        "empty_text_count": int(empty_text),
        "missing_title_count": int(missing_title),
        "text_length_chars": {
            "min": min(lengths) if lengths else None,
            "p50": percentile(lengths, 0.50),
            "p95": percentile(lengths, 0.95),
            "max": max(lengths) if lengths else None,
        },
        "single_chunk_doc_count": single_chunk_docs,
        "chunk_index_gap_doc_count": gap_docs,
        "chunks_per_doc": {
            "min": min((len(rows) for rows in grouped.values()), default=None),
            "p50": percentile([len(rows) for rows in grouped.values()], 0.50),
            "p95": percentile([len(rows) for rows in grouped.values()], 0.95),
            "max": max((len(rows) for rows in grouped.values()), default=None),
        },
    }


def vector_profile(hits: list[dict]) -> dict:
    dimensions: Counter[str] = Counter()
    norms: list[float] = []
    zero_vectors = 0
    models: Counter[str] = Counter()
    for hit in hits:
        source = hit.get("_source") or {}
        vector = source.get("embedding")
        if not isinstance(vector, list):
            continue
        dimensions[str(len(vector))] += 1
        norm = math.sqrt(sum(float(value) * float(value) for value in vector))
        norms.append(norm)
        zero_vectors += norm == 0
        if source.get("embedding_model"):
            models[str(source["embedding_model"])] += 1
    return {
        "sample_count": len(norms),
        "dimensions": dict(sorted(dimensions.items())),
        "zero_vector_count": int(zero_vectors),
        "norm": {
            "min": min(norms) if norms else None,
            "p50": percentile(norms, 0.50),
            "p95": percentile(norms, 0.95),
            "max": max(norms) if norms else None,
        },
        "embedding_models": dict(sorted(models.items())),
    }


def audit_index(base: str, index: str, expected: set[str]) -> dict:
    root = f"{base.rstrip('/')}/{index}"
    mapping_payload = request_json(root + "/_mapping")
    mapping = mapping_payload.get(index, mapping_payload)
    properties = mapping.get("mappings", {}).get("properties", {})
    health = request_json(f"{base.rstrip('/')}/_cluster/health/{index}")
    count = request_json(root + "/_count").get("count")
    aggregate = request_json(
        root + "/_search",
        {
            "size": 0,
            "query": {"terms": {"doc_id": sorted(expected)}},
            "aggs": {
                "target_doc_count": {"cardinality": {"field": "doc_id", "precision_threshold": 10000}},
                "target_chunk_count": {"value_count": {"field": "chunk_id"}},
                "embedding_models": {"terms": {"field": "embedding_model", "size": 20}},
                "missing_text": {"filter": {"bool": {"must_not": {"exists": {"field": "text"}}}}},
                "missing_embedding": {"filter": {"bool": {"must_not": {"exists": {"field": "embedding"}}}}},
            },
        },
    )
    target_query = {
        "size": 10000,
        "query": {"terms": {"doc_id": sorted(expected)}},
        "sort": [{"doc_id": "asc"}, {"chunk_index": "asc"}],
        "_source": ["doc_id", "chunk_id", "chunk_index", "title", "text"],
    }
    target_hits = request_json(root + "/_search", target_query).get("hits", {}).get("hits", [])
    vector_query = {
        "size": 500,
        "query": {"terms": {"doc_id": sorted(expected)}},
        "_source": ["doc_id", "chunk_id", "embedding", "embedding_model"],
    }
    vector_hits = request_json(root + "/_search", vector_query).get("hits", {}).get("hits", [])
    target_doc_ids = {
        str((hit.get("_source") or {}).get("doc_id"))
        for hit in target_hits
        if (hit.get("_source") or {}).get("doc_id")
    }
    aggs = aggregate.get("aggregations", {})
    return {
        "base": base,
        "index": index,
        "health": {key: health.get(key) for key in ("status", "number_of_nodes", "active_primary_shards", "unassigned_shards")},
        "index_document_count": count,
        "mapping": {
            "fields": sorted(properties),
            "embedding": properties.get("embedding"),
            "required_field_presence": {
                field: field in properties
                for field in ("doc_id", "chunk_id", "chunk_index", "title", "text", "embedding", "embedding_model")
            },
        },
        "target_coverage": {
            "expected_doc_count": len(expected),
            "target_doc_count_from_aggregation": aggs.get("target_doc_count", {}).get("value"),
            "target_doc_count_from_hits": len(target_doc_ids),
            "missing_doc_ids": sorted(expected - target_doc_ids),
            "target_chunk_count_from_aggregation": aggs.get("target_chunk_count", {}).get("value"),
            "missing_text_count": aggs.get("missing_text", {}).get("doc_count"),
            "missing_embedding_count": aggs.get("missing_embedding", {}).get("doc_count"),
            "embedding_models": aggs.get("embedding_models", {}).get("buckets", []),
        },
        "chunk_profile": profile_chunks(target_hits, expected),
        "vector_profile": vector_profile(vector_hits),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--o0-funnel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bge-es", default="http://127.0.0.1:9200")
    parser.add_argument("--bge-index", default="enterprise-rag-bge-small-v1")
    parser.add_argument("--conan-es", default="http://10.72.100.29:31920")
    parser.add_argument("--conan-index", default="enterprise-rag-qwen3-emb-v3-conan448")
    args = parser.parse_args()

    questions = load_jsonl(args.questions)
    funnel = json.loads(args.o0_funnel.read_text(encoding="utf-8"))
    raw = [
        row
        for row in funnel.get("rows", [])
        if row.get("bucket") == "raw_miss" and row.get("expected_document_ids")
    ]
    qids = [str(row["question_id"]) for row in raw if str(row["question_id"]) in questions]
    expected = {
        str(doc_id)
        for qid in qids
        for doc_id in questions[qid].get("expected_doc_ids", [])
        if doc_id
    }
    output = {
        "schema_version": 1,
        "scope": "O3.4 read-only index mapping/chunk/vector quality on O0 effective raw-miss",
        "question_count": len(qids),
        "expected_document_count": len(expected),
        "question_types": dict(sorted(Counter(str(questions[qid].get("question_type") or "unknown") for qid in qids).items())),
        "indices": {
            "bge": audit_index(args.bge_es, args.bge_index, expected),
            "conan": audit_index(args.conan_es, args.conan_index, expected),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
