"""Build a versioned BGE shadow index with metadata-only BM25 fields.

Vectors and original text are copied through Elasticsearch _reindex. Metadata
is then added by bulk update from the read-only manifest. No production alias
is touched and embeddings are never recomputed.
"""

from __future__ import annotations

import argparse
import copy
import json
import posixpath
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def request_json(url: str, payload: dict | str | None = None, method: str | None = None) -> dict:
    data = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode() if payload is not None else None
    request = Request(
        url,
        data=data,
        method=method or ("POST" if payload is not None else "GET"),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=300) as response:
        body = response.read().decode()
    return json.loads(body) if body else {}


def manifest_map(path: Path) -> dict[str, str]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        values: dict[str, str] = {}
        for doc_id, file_path in connection.execute(
            "SELECT doc_id,file_path FROM documents ORDER BY rowid"
        ):
            values.setdefault(str(doc_id), str(file_path or ""))
        return values
    finally:
        connection.close()


def metadata(file_path: str) -> tuple[str, str, str]:
    name = Path(file_path).name
    stem = name.rsplit(".", 1)[0]
    title = stem.split("__", 1)[1] if "__" in stem else stem
    parent = posixpath.dirname(file_path)
    section = parent.replace("\\", "/")
    lexical = " ".join(value for value in (title, section, file_path) if value)
    return title, section, lexical


def index_exists(base: str, index: str) -> bool:
    request = Request(f"{base.rstrip('/')}/{index}", method="HEAD")
    try:
        with urlopen(request, timeout=60):
            return True
    except HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def bulk_update(base: str, index: str, operations: list[str]) -> int:
    if not operations:
        return 0
    response = request_json(
        f"{base.rstrip('/')}/_bulk",
        "\n".join(operations) + "\n",
        method="POST",
    )
    if response.get("errors"):
        failures = []
        for item in response.get("items", []):
            detail = item.get("update") or {}
            if detail.get("error"):
                failures.append(detail.get("error"))
        raise RuntimeError(f"bulk metadata update failed ({len(failures)}); first={failures[:2]}")
    return len(operations) // 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--es", default="http://127.0.0.1:9200")
    parser.add_argument("--source-index", default="enterprise-rag-bge-small-v1")
    parser.add_argument("--target-index", default="o391_bge_meta_bm25_20260901")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--scroll", default="5m")
    parser.add_argument("--metadata-only", action="store_true", help="skip index creation/reindex and update an already completed target")
    args = parser.parse_args()

    root = args.es.rstrip("/")
    started = time.time()
    if args.metadata_only:
        if not index_exists(root, args.target_index):
            raise RuntimeError(f"target index does not exist: {args.target_index}")
        source_count = request_json(f"{root}/{args.source_index}/_count").get("count")
        target_count = request_json(f"{root}/{args.target_index}/_count").get("count")
        if source_count != target_count:
            raise RuntimeError(f"target count {target_count} does not match source count {source_count}")
        reindex = {"total": source_count}
        print(f"metadata-only update: {args.target_index} ({target_count} docs)", flush=True)
    else:
        source_mapping = request_json(f"{root}/{args.source_index}/_mapping")
        mapping_root = copy.deepcopy(source_mapping.get(args.source_index, source_mapping))
        mappings = mapping_root.get("mappings", {})
        properties = mappings.setdefault("properties", {})
        properties.update({
            "title": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 512}}},
            "file_path": {"type": "keyword", "ignore_above": 2048},
            "section_context": {"type": "text"},
            "lexical_context": {"type": "text"},
        })
        if index_exists(root, args.target_index):
            raise RuntimeError(f"target index already exists: {args.target_index}")
        request_json(f"{root}/{args.target_index}", {"mappings": mappings}, method="PUT")
        print(f"reindex {args.source_index} -> {args.target_index}", flush=True)
        reindex = request_json(
            f"{root}/_reindex?wait_for_completion=true&refresh=false",
            {
                "source": {"index": args.source_index},
                "dest": {"index": args.target_index, "op_type": "create"},
            },
        )
        print(json.dumps({key: reindex.get(key) for key in ("took", "total", "created", "updated", "version_conflicts", "failures")}, ensure_ascii=False), flush=True)
        if reindex.get("failures") or reindex.get("version_conflicts"):
            raise RuntimeError(f"reindex failed: {reindex}")

    paths = manifest_map(args.manifest)
    cache = {doc_id: metadata(path) for doc_id, path in paths.items()}
    print(f"metadata map: {len(cache)} unique doc_ids", flush=True)

    search = request_json(
        f"{root}/{args.source_index}/_search?scroll={args.scroll}",
        {"size": args.batch_size, "query": {"match_all": {}}, "_source": ["doc_id", "chunk_id"]},
    )
    scroll_id = search.get("_scroll_id")
    total = 0
    missing_map = 0
    batches: list[list[str]] = []
    pool = ThreadPoolExecutor(max_workers=max(1, args.workers))
    futures = []
    try:
        while True:
            hits = (search.get("hits") or {}).get("hits") or []
            if not hits:
                break
            operations: list[str] = []
            for hit in hits:
                source = hit.get("_source") or {}
                doc_id = str(source.get("doc_id") or "")
                chunk_id = str(source.get("chunk_id") or hit.get("_id") or "")
                values = cache.get(doc_id)
                if values is None:
                    missing_map += 1
                    values = ("", "", "")
                title, section, lexical = values
                operations.append(json.dumps({"update": {"_index": args.target_index, "_id": hit.get("_id")}}, separators=(",", ":")))
                operations.append(json.dumps({"doc": {"title": title, "file_path": paths.get(doc_id, ""), "section_context": section, "lexical_context": lexical}}, ensure_ascii=False, separators=(",", ":")))
            futures.append(pool.submit(bulk_update, root, args.target_index, operations))
            total += len(hits)
            if len(futures) >= max(1, args.workers):
                futures.pop(0).result()
            if total % 50000 < args.batch_size:
                print(f"metadata updates scanned={total}", flush=True)
            if not scroll_id:
                break
            search = request_json(
                f"{root}/_search/scroll",
                {"scroll": args.scroll, "scroll_id": scroll_id},
            )
            scroll_id = search.get("_scroll_id", scroll_id)
        for future in futures:
            future.result()
    finally:
        pool.shutdown(wait=True)
        if scroll_id:
            try:
                request_json(f"{root}/_search/scroll", {"scroll_id": [scroll_id]}, method="DELETE")
            except Exception:
                pass
    request_json(f"{root}/{args.target_index}/_refresh", {}, method="POST")
    target_count = request_json(f"{root}/{args.target_index}/_count").get("count")
    print(json.dumps({"target_index": args.target_index, "source_count": reindex.get("total"), "target_count": target_count, "metadata_scanned": total, "missing_manifest_map": missing_map, "elapsed_sec": round(time.time() - started, 1)}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
