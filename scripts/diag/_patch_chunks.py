"""Patch chunks.jsonl v3: parallel re-chunk of oversized docs.

Faster: batch-tokenize scan + ProcessPoolExecutor re-chunking (8 workers).
"""
import hashlib
import json
import os
import sqlite3
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, "/opt/enterprise-rag-bench/app")

CHUNKS = "/opt/enterprise-rag-bench/app/.index_cache/full_es_qwen3_emb/chunks.jsonl"
MANIFEST = "/opt/enterprise-rag-bench/app/.index_cache/full_es_qwen3_emb/manifest.sqlite3"
CORPUS = "/opt/enterprise-rag-bench/app/corpus/all_documents"
SIZE, OVERLAP = 384, 64
HARD_LIMIT = SIZE + OVERLAP
VERSION = "hierarchical-v1"
BATCH = 4096
WORKERS = 8


def _rechunk_doc(args) -> tuple[str, list[dict]]:
    doc_id, rel_path, is_dup = args
    from src.indexer import _chunk_text_hierarchical

    full_path = os.path.join(CORPUS, rel_path)
    try:
        with open(full_path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return doc_id, []
    chunks = _chunk_text_hierarchical(text, SIZE, OVERLAP)
    path_tag = hashlib.sha256(rel_path.encode("utf-8")).hexdigest()[:12]
    records = []
    for i, cd in enumerate(chunks):
        if is_dup:
            cid = f"{doc_id}__{VERSION}__dup-{path_tag}__chunk{i:05d}"
        else:
            cid = f"{doc_id}__{VERSION}__chunk{i:05d}"
        records.append({
            "chunk_id": cid,
            "doc_id": doc_id,
            "source_type": rel_path.split("/")[0],
            "text": cd["text"],
            "char_start": cd["start"],
            "char_end": cd["end"],
        })
    return doc_id, records


def main() -> int:
    from src.indexer import _get_tokenizer

    tokenizer = _get_tokenizer()

    # 1) load records + batch scan
    records: list[dict] = []
    with open(CHUNKS, encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line))
    print(f"loaded {len(records)} chunks", flush=True)

    bad_doc_ids: set[str] = set()
    for start in range(0, len(records), BATCH):
        batch = records[start:start + BATCH]
        enc = tokenizer(
            [r["text"] for r in batch],
            add_special_tokens=False,
            verbose=False,
        )
        for r, ids in zip(batch, enc["input_ids"]):
            if len(ids) > HARD_LIMIT:
                bad_doc_ids.add(r["doc_id"])
    print(f"docs with oversized chunks: {len(bad_doc_ids)}", flush=True)
    if not bad_doc_ids:
        print("no patch needed")
        return 0

    # 2) manifest paths + duplicates
    conn = sqlite3.connect(MANIFEST)
    rows = conn.execute("SELECT file_path, doc_id FROM documents").fetchall()
    conn.close()
    path_by_doc: dict[str, str] = {d: p for p, d in rows}
    dup_counts: dict[str, int] = {}
    for _, d in rows:
        dup_counts[d] = dup_counts.get(d, 0) + 1
    duplicate_doc_ids = {d for d, n in dup_counts.items() if n > 1}

    # 3) parallel re-chunk
    tasks = [
        (doc_id, path_by_doc.get(doc_id), doc_id in duplicate_doc_ids)
        for doc_id in sorted(bad_doc_ids)
        if path_by_doc.get(doc_id)
    ]
    fresh: dict[str, list[dict]] = {}
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(_rechunk_doc, t) for t in tasks]
        done = 0
        for fut in as_completed(futures):
            doc_id, recs = fut.result()
            if recs:
                fresh[doc_id] = recs
            done += 1
            if done % 1000 == 0:
                print(f"  re-chunked {done}/{len(tasks)}", flush=True)
    print(f"re-chunked docs: {len(fresh)}", flush=True)

    # 4) rewrite
    fresh_doc_ids = set(fresh)
    out_path = CHUNKS + ".patched"
    kept = replaced = 0
    with open(out_path, "w", encoding="utf-8") as g:
        for r in records:
            if r["doc_id"] in fresh_doc_ids:
                replaced += 1
                continue
            g.write(json.dumps(r, ensure_ascii=False) + "\n")
            kept += 1
        for new_records in fresh.values():
            for r in new_records:
                g.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(out_path, CHUNKS)
    print(
        f"rewritten: kept {kept}, replaced {replaced}, "
        f"added {sum(len(v) for v in fresh.values())}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
