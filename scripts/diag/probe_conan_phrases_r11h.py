import json
import urllib.parse
import urllib.request

BASE = "http://10.72.100.29:31920/enterprise-rag-qwen3-emb-v3-conan448/_search"
phrases = [
    "logs are only retained for 90 days",
    "Tuesday October 24 2028 10:00 AM Pacific",
    "12-month retention ingestion audit traces monthly exports",
    "400 queries per second overnight vectorization",
    "under 150 ms top 10 results",
    "2 to 4 weeks provisioning customer key management",
]
for phrase in phrases:
    body = {"size": 1, "query": {"match_phrase": {"text": phrase}}, "_source": ["doc_id", "source_type", "text"]}
    req = urllib.request.Request(BASE, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            out = json.load(r)
        hits = out.get("hits", {}).get("hits", [])
        print(json.dumps({"phrase": phrase, "total": out.get("hits", {}).get("total"), "hit": hits[0] if hits else None}, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"phrase": phrase, "error": type(exc).__name__}))
