"""Read-only inspection of dense-vector fields on an Elasticsearch endpoint."""

from __future__ import annotations

import argparse
import json
from urllib.request import urlopen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://10.72.55.201:31920")
    args = ap.parse_args()
    with urlopen(args.url.rstrip("/") + "/_mapping", timeout=60) as response:
        mapping = json.loads(response.read().decode())
    with urlopen(args.url.rstrip("/") + "/_cat/indices?format=json&h=index,docs.count,store.size", timeout=60) as response:
        catalog = {row.get("index"): row for row in json.loads(response.read().decode())}
    dense = []
    for index, payload in mapping.items():
        props = payload.get("mappings", {}).get("properties", {})
        vectors = {
            name: {
                "dims": value.get("dims"),
                "similarity": value.get("similarity"),
                "index": value.get("index"),
                "index_options": value.get("index_options"),
            }
            for name, value in props.items()
            if value.get("type") == "dense_vector"
        }
        if vectors:
            dense.append({"index": index, "docs": catalog.get(index, {}).get("docs.count"), "store": catalog.get(index, {}).get("store.size"), "vectors": vectors, "fields": sorted(props)})
    dims = {}
    for row in dense:
        key = tuple(sorted((value.get("dims") for value in row["vectors"].values())))
        dims[str(key)] = dims.get(str(key), 0) + 1
    dense.sort(key=lambda row: int(str(row.get("docs") or "0").replace(",", "") or 0), reverse=True)
    summary = {"indices_with_dense_vectors": len(dense), "dimension_counts": dims, "largest_20": dense[:20]}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
