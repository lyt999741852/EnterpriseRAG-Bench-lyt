"""Validate chunks against the tokenizer used by multilingual-e5-large."""

from __future__ import annotations

import json
import math
import os
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

DEFAULT_E5_LIMIT = 512
DEFAULT_E5_SAFETY_LIMIT = 480
DEFAULT_E5_CHUNK_SIZE = 384
DEFAULT_E5_OVERLAP = 64


def _value(record: Any, key: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(key, default)
    return getattr(record, key, default)


def load_tokenizer(model_name: str):
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(model_name, local_files_only=True)


def _summary(values: Counter[int]) -> dict[str, int | float]:
    if not values:
        return {"min": 0, "p50": 0, "p90": 0, "p95": 0, "p99": 0, "max": 0, "mean": 0.0}
    keys = sorted(values)
    total = sum(values.values())

    def percentile(q: float) -> int:
        rank = max(1, math.ceil(q * total))
        cumulative = 0
        for key in keys:
            cumulative += values[key]
            if cumulative >= rank:
                return int(key)
        return int(keys[-1])

    return {"min": keys[0], "p50": percentile(.50), "p90": percentile(.90),
            "p95": percentile(.95), "p99": percentile(.99), "max": keys[-1],
            "mean": round(sum(key * count for key, count in values.items()) / total, 3)}


def _estimated_split_count(token_count: int, size: int, overlap: int) -> int:
    if token_count <= size:
        return 1
    return 1 + math.ceil((token_count - size) / max(1, size - overlap))


def audit_records(records: Iterable[Any], tokenizer: Any, *, batch_size: int = 512,
                  max_tokens: int = DEFAULT_E5_LIMIT,
                  safety_limit: int = DEFAULT_E5_SAFETY_LIMIT,
                  recommended_size: int = DEFAULT_E5_CHUNK_SIZE,
                  recommended_overlap: int = DEFAULT_E5_OVERLAP) -> dict[str, Any]:
    if not 0 < safety_limit <= max_tokens:
        raise ValueError("safety_limit must be positive and <= max_tokens")
    if not 0 <= recommended_overlap < recommended_size:
        raise ValueError("recommended_overlap must be >= 0 and < recommended_size")
    total = 0
    docs: set[str] = set()
    seen_ids: set[str] = set()
    duplicate_ids = invalid_records = oversized = over_limit = 0
    estimated_after_split = 0
    token_lengths: Counter[int] = Counter()
    batch: list[Any] = []

    def consume(items: list[Any]) -> None:
        nonlocal total, duplicate_ids, invalid_records, oversized, over_limit
        nonlocal estimated_after_split
        texts = [str(_value(item, "text", "")) for item in items]
        encoded = tokenizer(texts, add_special_tokens=False, truncation=False,
                            padding=False, verbose=False)
        for item, token_count in zip(items, (len(ids) for ids in encoded["input_ids"])):
            total += 1
            token_lengths[token_count] += 1
            chunk_id, doc_id, text = (_value(item, "chunk_id"), _value(item, "doc_id"),
                                      _value(item, "text"))
            if not chunk_id or not doc_id or not isinstance(text, str):
                invalid_records += 1
            if chunk_id in seen_ids:
                duplicate_ids += 1
            else:
                seen_ids.add(str(chunk_id))
            docs.add(str(doc_id))
            if token_count > safety_limit:
                oversized += 1
                estimated_after_split += _estimated_split_count(token_count, recommended_size, recommended_overlap)
            else:
                estimated_after_split += 1
            if token_count > max_tokens:
                over_limit += 1

    for record in records:
        batch.append(record)
        if len(batch) >= max(1, batch_size):
            consume(batch)
            batch = []
    if batch:
        consume(batch)
    stats = _summary(token_lengths)
    return {
        "tokenizer": {"model_name": getattr(tokenizer, "name_or_path", "unknown"),
                      "model_max_length": getattr(tokenizer, "model_max_length", None),
                      "add_special_tokens": False},
        "limits": {"model_window": max_tokens, "safety_limit": safety_limit,
                    "recommended_chunk_size": recommended_size,
                    "recommended_overlap": recommended_overlap},
        "chunks": {"total": total, "documents": len(docs),
                    "invalid_records": invalid_records, "duplicate_chunk_ids": duplicate_ids,
                    "token_length": stats, "over_safety_limit": oversized,
                    "over_model_window": over_limit,
                    "estimated_total_after_safe_split": estimated_after_split,
                    "estimated_added_chunks": max(0, estimated_after_split - total)},
        "safe_for_embedding": not any((invalid_records, duplicate_ids, oversized, over_limit)),
    }


def audit_jsonl(chunks_path: str | os.PathLike[str], tokenizer: Any, **kwargs: Any) -> dict[str, Any]:
    with Path(chunks_path).open(encoding="utf-8") as handle:
        return audit_records((json.loads(line) for line in handle if line.strip()), tokenizer, **kwargs)


def write_report(report: dict[str, Any], path: str | os.PathLike[str]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, target)
