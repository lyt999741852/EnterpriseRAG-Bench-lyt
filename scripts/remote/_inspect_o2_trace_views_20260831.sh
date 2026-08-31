set -euo pipefail
python3 - <<'PY'
import json

path = "/opt/enterprise-rag-bench/app/outputs/pageindex_full500_bge_dpv4_20260831/route_trace.jsonl"
wanted = {"qst_0197", "qst_0231", "qst_0272", "qst_0362", "qst_0447"}
with open(path, encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("question_id") not in wanted:
            continue
        print("===", row["question_id"], "===")
        stages = row.get("retrieval_stages") or {}
        for view in stages.get("views", []):
            print(view.get("view"), sorted(view.keys()),
                  "chunks", len(view.get("chunk_ids") or []),
                  "docs", len(view.get("document_ids") or []),
                  "first_docs", (view.get("document_ids") or [])[:8])
PY
