"""Build a one-profile-per-document shadow index from the metadata shadow.

This is a read-only experiment.  It keeps the existing chunk-0 vector and
creates a profile_text field from the first chunk plus audited metadata; no
embedding is recomputed and no production alias is changed.
"""
from __future__ import annotations

import argparse
import copy
import json
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def request_json(url: str, payload: dict | str | None = None, method: str | None = None) -> dict:
    data = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode() if payload is not None else None
    req = Request(url, data=data, method=method or ("POST" if payload is not None else "GET"), headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=300) as response:
            body = response.read().decode()
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:2000]}") from exc
    return json.loads(body) if body else {}


def exists(root: str, index: str) -> bool:
    try:
        with urlopen(Request(f"{root}/{index}", method="HEAD"), timeout=60):
            return True
    except HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--es", default="http://127.0.0.1:9200")
    ap.add_argument("--source-index", default="o391_bge_meta_bm25_20260901")
    ap.add_argument("--target-index", default="o392_bge_doc_profile_20260901")
    args = ap.parse_args()
    root = args.es.rstrip("/")
    if exists(root, args.target_index):
        raise RuntimeError(f"target exists: {args.target_index}")
    source = request_json(f"{root}/{args.source_index}/_mapping")
    source_root = source.get(args.source_index, source)
    mappings = copy.deepcopy(source_root.get("mappings", {}))
    properties = mappings.setdefault("properties", {})
    properties["profile_text"] = {"type": "text"}
    properties["profile_id"] = {"type": "keyword", "ignore_above": 256}
    # profile documents contain one source chunk; retain only fields needed by
    # profile retrieval and expansion diagnostics.
    # Preserve auxiliary source fields because the source mapping is strict;
    # only the large text field is removed after it is copied to profile_text.
    properties.pop("text", None)
    mappings["properties"] = properties
    request_json(f"{root}/{args.target_index}", {"mappings": mappings}, method="PUT")
    started = time.time()
    body = {
        "source": {"index": args.source_index, "query": {"term": {"chunk_index": 0}}},
        "dest": {"index": args.target_index, "op_type": "create"},
        "script": {"lang": "painless", "source": "ctx._source.profile_text = ctx._source.text; ctx._source.profile_id = ctx._source.doc_id; ctx._source.remove('text');"},
    }
    result = request_json(f"{root}/_reindex?wait_for_completion=true&refresh=false", body)
    print(json.dumps({key: result.get(key) for key in ("took", "total", "created", "version_conflicts", "failures")}, ensure_ascii=False), flush=True)
    if result.get("failures") or result.get("version_conflicts"):
        raise RuntimeError(f"reindex failed: {result}")
    request_json(f"{root}/{args.target_index}/_refresh", method="POST")
    count = request_json(f"{root}/{args.target_index}/_count").get("count")
    print(json.dumps({"target_index": args.target_index, "profile_count": count, "elapsed_sec": round(time.time() - started, 1)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
