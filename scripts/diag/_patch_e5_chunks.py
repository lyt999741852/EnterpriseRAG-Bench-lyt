"""Patch chunks.jsonl for e5 tokenizer: re-split chunks > 480 e5-tokens.

Uses the e5 (XLM-R) tokenizer's offset mapping for exact token-boundary cuts.
New pieces get chunk_id suffix __e5pN and are written back in place.
"""
import json
import os
import sys

sys.path.insert(0, "/opt/enterprise-rag-bench/app")

from transformers import AutoTokenizer

CHUNKS = "/opt/enterprise-rag-bench/app/.index_cache/full_es_qwen3_emb/chunks.jsonl"
E5_PATH = "/data06/embedding-models/multilingual-e5-large"
LIMIT = 480
SIZE, OVERLAP = 384, 64
BATCH = 4096


def hard_split(text: str, tok, size: int = SIZE, overlap: int = OVERLAP) -> list[str]:
    enc = tok(text, add_special_tokens=False, return_offsets_mapping=True, truncation=False)
    offsets = enc["offset_mapping"]
    n = len(offsets)
    if n <= size:
        return [text]
    step = size - overlap if overlap < size else 1
    parts: list[str] = []
    i = 0
    while i < n:
        end_i = min(i + size, n)
        part = text[offsets[i][0]:offsets[end_i - 1][1]]
        if part.strip():
            parts.append(part)
        i += step
    return parts or [text]


def main() -> int:
    tok = AutoTokenizer.from_pretrained(E5_PATH, local_files_only=True)
    records: list[dict] = []
    with open(CHUNKS, encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line))
    print(f"loaded {len(records)} chunks", flush=True)

    # find oversized chunk indices (batch tokenize)
    bad_idx: list[int] = []
    for start in range(0, len(records), BATCH):
        batch = records[start:start + BATCH]
        enc = tok([r["text"] for r in batch], add_special_tokens=False, verbose=False)
        for i, ids in enumerate(enc["input_ids"]):
            if len(ids) > LIMIT:
                bad_idx.append(start + i)
    print(f"oversized chunks (e5 tokens>{LIMIT}): {len(bad_idx)}", flush=True)
    if not bad_idx:
        print("no patch needed")
        return 0

    # re-split each oversized chunk; build replacement records
    replacements: dict[int, list[dict]] = {}
    for idx in bad_idx:
        rec = records[idx]
        parts = hard_split(rec["text"], tok)
        new_recs = []
        for j, part in enumerate(parts):
            new_recs.append({
                "chunk_id": f"{rec['chunk_id']}__e5p{j}",
                "doc_id": rec["doc_id"],
                "source_type": rec["source_type"],
                "text": part,
                "char_start": rec["char_start"],
                "char_end": rec["char_start"] + len(part),
            })
        replacements[idx] = new_recs

    # rewrite
    out_path = CHUNKS + ".patched"
    kept = replaced = added = 0
    with open(out_path, "w", encoding="utf-8") as g:
        for i, rec in enumerate(records):
            if i in replacements:
                replaced += 1
                for nr in replacements[i]:
                    g.write(json.dumps(nr, ensure_ascii=False) + "\n")
                    added += 1
                continue
            g.write(json.dumps(rec, ensure_ascii=False) + "\n")
            kept += 1
    os.replace(out_path, CHUNKS)
    print(f"rewritten: kept {kept}, replaced {replaced}, added {added}", flush=True)

    # verify: scan again
    over = 0
    batch = []
    with open(CHUNKS, encoding="utf-8") as f:
        for line in f:
            batch.append(json.loads(line))
            if len(batch) >= BATCH:
                enc = tok([r["text"] for r in batch], add_special_tokens=False, verbose=False)
                over += sum(1 for ids in enc["input_ids"] if len(ids) > LIMIT)
                batch = []
    if batch:
        enc = tok([r["text"] for r in batch], add_special_tokens=False, verbose=False)
        over += sum(1 for ids in enc["input_ids"] if len(ids) > LIMIT)
    print(f"verify: remaining oversized > {LIMIT}: {over}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
