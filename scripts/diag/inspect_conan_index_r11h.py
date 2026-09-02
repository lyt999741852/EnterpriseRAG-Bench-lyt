import json
import urllib.request

BASE = "http://10.72.100.29:31920"
INDEX = "enterprise-rag-qwen3-emb-v3-conan448"


def get(path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


mapping = get(f"/{INDEX}")
count = get(f"/{INDEX}/_count")
aggs = get(
    f"/{INDEX}/_search",
    {
        "size": 0,
        "aggs": {
            "embedding_models": {"terms": {"field": "embedding_model", "size": 20}},
            "source_types": {"terms": {"field": "source_type", "size": 20}},
        },
    },
)
sample = get(
    f"/{INDEX}/_search",
    {
        "size": 2,
        "_source": [
            "doc_id",
            "chunk_id",
            "chunk_index",
            "embedding_model",
            "source_type",
            "text",
        ],
    },
)
props = mapping[INDEX]["mappings"]["properties"]
print(json.dumps({
    "index": INDEX,
    "aliases": mapping[INDEX].get("aliases", {}),
    "count": count.get("count"),
    "embedding": props.get("embedding"),
    "fields": sorted(props),
    "embedding_models": aggs["aggregations"]["embedding_models"]["buckets"],
    "source_types": aggs["aggregations"]["source_types"]["buckets"],
    "sample": sample.get("hits", {}).get("hits", []),
}, ensure_ascii=False, indent=2))
