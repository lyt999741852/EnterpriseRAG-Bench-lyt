"""Build isolated BGE-small A/B indices for chunk/context quality validation.

Variant A matches the current 512-token, zero-overlap text-only representation.
Variant B uses 448/64 chunks and prepends stable path/title/channel context.
Only the 61 gold documents from O0 are indexed; production indices are never
modified.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
from sentence_transformers import SentenceTransformer


def call_json(url: str, payload: dict | None = None, method: str | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(
        url,
        data=data,
        method=method or ("POST" if payload is not None else "GET"),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode())


def load_questions(path: Path) -> set[str]:
    return {
        str(doc_id)
        for row in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
        for doc_id in row.get("expected_doc_ids", [])
        if doc_id
    }


def load_target_docs(corpus: Path, expected: set[str]) -> list[tuple[str, Path, str, str]]:
    found: list[tuple[str, Path, str, str]] = []
    for path in sorted(corpus.rglob("*.txt")):
        doc_id = path.name.split("__", 1)[0]
        if doc_id not in expected:
            continue
        rel = path.relative_to(corpus).as_posix()
        slug = path.stem.split("__", 1)[1] if "__" in path.stem else path.stem
        title = re.sub(r"[-_]+", " ", slug).strip()
        text = path.read_text(encoding="utf-8", errors="replace")
        found.append((doc_id, path, rel, title))
    return found


def split_words(text: str, size: int, overlap: int) -> list[tuple[str, int, int]]:
    tokens = list(re.finditer(r"\S+", text))
    if len(tokens) <= size:
        return [(text, 0, len(text))]
    step = max(1, size - overlap)
    chunks: list[tuple[str, int, int]] = []
    for start in range(0, len(tokens), step):
        end_i = min(start + size, len(tokens))
        start_char = tokens[start].start()
        end_char = tokens[end_i - 1].end()
        chunks.append((text[start_char:end_char], start_char, end_char))
        if end_i == len(tokens):
            break
    return chunks


def make_records(docs: list[tuple[str, Path, str, str]], variant: str) -> list[dict]:
    records: list[dict] = []
    size, overlap = (512, 0) if variant == "a" else (448, 64)
    for doc_id, path, rel, title in docs:
        original = path.read_text(encoding="utf-8", errors="replace")
        first_line = next((line.strip() for line in original.splitlines() if line.strip()), "")
        prefix = f"source_path: {rel}\ntitle: {title}\nsection_context: {first_line}\n"
        for index, (chunk, start, end) in enumerate(split_words(original, size, overlap)):
            enriched = chunk if variant == "a" else prefix + chunk
            records.append(
                {
                    "chunk_id": f"{doc_id}__quality_{variant}_{index}",
                    "doc_id": doc_id,
                    "source_type": path.parent.name,
                    "text": enriched,
                    "raw_text": chunk,
                    "title": title,
                    "section_path": rel,
                    "chunk_index": index,
                    "char_start": start,
                    "char_end": end,
                }
            )
    return records


def create_index(base: str, index: str, dimension: int, overwrite: bool) -> None:
    exists = call_json(f"{base.rstrip('/')}/{index}", method="HEAD") if False else None
    try:
        call_json(f"{base.rstrip('/')}/{index}")
        if not overwrite:
            raise RuntimeError(f"index already exists: {index}")
        call_json(f"{base.rstrip('/')}/{index}", method="DELETE")
    except Exception as exc:
        if "HTTP Error 404" not in str(exc) and "HTTP 404" not in str(exc) and "not found" not in str(exc).lower():
            if "already exists" in str(exc):
                raise
    body = {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0, "refresh_interval": "30s"},
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "chunk_id": {"type": "keyword"},
                "doc_id": {"type": "keyword"},
                "source_type": {"type": "keyword"},
                "text": {"type": "text"},
                "raw_text": {"type": "text"},
                "title": {"type": "text"},
                "section_path": {"type": "keyword"},
                "chunk_index": {"type": "integer"},
                "char_start": {"type": "integer"},
                "char_end": {"type": "integer"},
                "embedding_model": {"type": "keyword"},
                "embedding": {"type": "dense_vector", "dims": dimension, "index": True, "similarity": "cosine"},
            },
        },
    }
    call_json(f"{base.rstrip('/')}/{index}", body, method="PUT")


def bulk_index(base: str, index: str, records: list[dict], vectors: np.ndarray, batch_size: int = 256) -> None:
    for start in range(0, len(records), batch_size):
        lines: list[str] = []
        for offset, (record, vector) in enumerate(zip(records[start:start + batch_size], vectors[start:start + batch_size])):
            lines.append(json.dumps({"index": {"_index": index, "_id": record["chunk_id"]}}, separators=(",", ":")))
            document = dict(record)
            document["embedding_model"] = "BAAI/bge-small-en-v1.5"
            document["embedding"] = vector.tolist()
            lines.append(json.dumps(document, ensure_ascii=False, separators=(",", ":")))
        req = Request(
            f"{base.rstrip('/')}/_bulk",
            data=("\n".join(lines) + "\n").encode(),
            method="POST",
            headers={"Content-Type": "application/x-ndjson"},
        )
        with urlopen(req, timeout=180) as response:
            result = json.loads(response.read().decode())
        failures = [item for item in result.get("items", []) if item.get("index", {}).get("status", 500) >= 300]
        if failures:
            raise RuntimeError(f"bulk failures in {index}: {failures[:2]}")
    call_json(f"{base.rstrip('/')}/{index}/_refresh", method="POST")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--o0-funnel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--es", default="http://127.0.0.1:9200")
    parser.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    funnel = json.loads(args.o0_funnel.read_text(encoding="utf-8"))
    raw_qids = {
        str(row["question_id"])
        for row in funnel.get("rows", [])
        if row.get("bucket") == "raw_miss" and row.get("expected_document_ids")
    }
    question_rows = {
        str(row["question_id"]): row
        for row in (json.loads(line) for line in args.questions.read_text(encoding="utf-8").splitlines())
    }
    expected = {
        str(doc_id)
        for qid in raw_qids
        for doc_id in question_rows.get(qid, {}).get("expected_doc_ids", [])
        if doc_id
    }
    docs = load_target_docs(args.corpus, expected)
    if {doc_id for doc_id, *_ in docs} != expected:
        raise RuntimeError("corpus target document set is incomplete")
    model = SentenceTransformer(args.model, device=args.device, local_files_only=True)
    dimension = int(model.get_sentence_embedding_dimension())
    variants = {}
    for variant, index in (("a", "o34_quality_a_bge_small_20260831"), ("b", "o34_quality_b_bge_small_20260831")):
        records = make_records(docs, variant)
        texts = [record["text"] for record in records]
        vectors = np.asarray(model.encode(texts, batch_size=args.batch_size, normalize_embeddings=True, show_progress_bar=True), dtype=np.float32)
        if vectors.shape != (len(records), dimension):
            raise RuntimeError(f"unexpected vectors for {variant}: {vectors.shape}")
        create_index(args.es, index, dimension, args.overwrite)
        bulk_index(args.es, index, records, vectors)
        count = call_json(f"{args.es.rstrip('/')}/{index}/_count").get("count")
        variants[variant] = {
            "index": index,
            "doc_count": len({record["doc_id"] for record in records}),
            "chunk_count": len(records),
            "chunk_size": 512 if variant == "a" else 448,
            "chunk_overlap": 0 if variant == "a" else 64,
            "es_count": count,
        }
        print(f"variant {variant}: docs={variants[variant]['doc_count']} chunks={len(records)} es_count={count}", flush=True)
    output = {
        "schema_version": 1,
        "scope": "isolated BGE-small A/B index for 61 O0 gold documents",
        "question_count": len(raw_qids),
        "expected_document_count": len(expected),
        "embedding_model": args.model,
        "embedding_dimension": dimension,
        "variants": variants,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
