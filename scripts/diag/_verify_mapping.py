"""Verify ES mapping and gold doc existence query validity."""
import json
import sys

sys.path.insert(0, "/opt/enterprise-rag-bench/app")

from src.elasticsearch_backend import ElasticsearchBackend, ElasticsearchConfig  # noqa: E402

INDEX = "enterprise-rag-bge-small-v1"


def main() -> None:
    backend = ElasticsearchBackend(ElasticsearchConfig(index_name=INDEX))
    m = backend._request("GET", f"/{INDEX}/_mapping")
    props = m[INDEX]["mappings"]["properties"]
    print("doc_id mapping:", props.get("doc_id"))
    print("chunk_id mapping:", props.get("chunk_id"))

    r = backend._request("GET", f"/{INDEX}/_search", {"size": 1})
    src = r["hits"]["hits"][0]["_source"]
    print("sample doc_id:", src.get("doc_id"))
    print("sample chunk_id:", src.get("chunk_id"))

    for line in open("/opt/enterprise-rag-bench/app/questions.jsonl"):
        q = json.loads(line)
        if q["question_id"] == "qst_0298":
            gold = q.get("expected_doc_ids") or []
            print("qst_0298 gold:", gold)
            for g in gold:
                for field in ("doc_id.keyword", "doc_id"):
                    body = {"query": {"term": {field: g}}, "size": 0}
                    resp = backend._request("GET", f"/{INDEX}/_search", body)
                    print(f"  term {field}:", resp.get("hits", {}).get("total"))
            break


if __name__ == "__main__":
    main()
