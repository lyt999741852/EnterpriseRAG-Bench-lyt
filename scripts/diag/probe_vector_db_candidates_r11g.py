"""Read-only identify likely full Conan indexes and benchmark-document coverage."""

from __future__ import annotations

import argparse
import json
from urllib.request import Request, urlopen


def get(base: str, path: str) -> object:
    with urlopen(base.rstrip("/") + path, timeout=60) as response:
        return json.loads(response.read().decode())


def post(base: str, path: str, body: dict) -> object:
    req = Request(base.rstrip("/") + path, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://10.72.55.201:31920")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    catalog = {row.get("index"): row for row in get(args.url, "/_cat/indices?format=json&h=index,docs.count,store.size")}
    names = ["doc_panda2", "test_wiki_data_v1"]
    rows = []
    probes = [("soc2", "SOC2 readiness retention"), ("healthcare", "healthcare patient connector retention"), ("partner", "partner isolated customer environment")]
    for index in names:
        mapping = get(args.url, f"/{index}/_mapping")
        payload = mapping.get(index, {})
        props = payload.get("mappings", {}).get("properties", {})
        metadata = props.get("metadata", {})
        row = {"index": index, "docs": catalog.get(index, {}).get("docs.count"), "store": catalog.get(index, {}).get("store.size"), "fields": sorted(props), "vector": {k: {x: v.get(x) for x in ("type", "dims", "index", "similarity", "index_options")} for k, v in props.items() if v.get("type") == "dense_vector"}, "metadata_mapping": metadata}
        row["probes"] = {}
        for name, text in probes:
            # These indices expose metadata as an object whose subfields vary;
            # probe the stable full-text field first to avoid dynamic-field
            # query errors.
            result = post(args.url, f"/{index}/_search", {"size": 3, "_source": ["text", "metadata"], "query": {"match": {"text": text}}})
            hits = result.get("hits", {}).get("hits", [])
            row["probes"][name] = [{"id": hit.get("_id"), "score": hit.get("_score"), "source_keys": sorted((hit.get("_source") or {}).keys()), "text_preview": str((hit.get("_source") or {}).get("text", ""))[:180], "metadata_preview": str((hit.get("_source") or {}).get("metadata", ""))[:500]} for hit in hits]
        rows.append(row)
    global_probes = {}
    for name, text in [("soc2", "logs are only retained for 90 days"), ("deep_dive", "Tuesday October 24 2028 10:00 AM Pacific"), ("redwood", "12-month retention ingestion audit traces monthly exports"), ("vectorization", "400 queries per second overnight vectorization"), ("latency", "under 150 ms top 10 results"), ("key_management", "2 to 4 weeks provisioning customer key management")]:
        result = post(args.url, "/_search", {"size": 10, "_source": ["text", "metadata"], "query": {"match_phrase": {"text": text}}})
        global_probes[name] = [{"index": hit.get("_index"), "id": hit.get("_id"), "score": hit.get("_score"), "text_preview": str((hit.get("_source") or {}).get("text", ""))[:180]} for hit in result.get("hits", {}).get("hits", [])]
    output = {"schema_version": 1, "scope": "R11.G vector database candidate identification", "endpoint": args.url, "indices": rows, "global_probes": global_probes}
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
    print(json.dumps({"indices": [{"index": row["index"], "docs": row["docs"], "vector": row["vector"], "probe_hit_counts": {k: len(v) for k, v in row["probes"].items()}} for row in rows], "global_probes": {k: [{"index": h["index"], "score": h["score"]} for h in v] for k, v in global_probes.items()}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
