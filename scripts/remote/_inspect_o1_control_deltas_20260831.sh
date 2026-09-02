set -euo pipefail
python3 - <<'PY'
import json

def load(path):
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                out[str(row["question_id"])] = row
    return out

base = load("/opt/enterprise-rag-bench/app/outputs/pageindex_full500_bge_dpv4_20260831/route_trace.jsonl")
o1 = load("/opt/enterprise-rag-bench/app/outputs/pageindex_o1_original_reserve_smoke20_20260831/route_trace.jsonl")
for qid in ("qst_0050", "qst_0410", "qst_0450", "qst_0197", "qst_0272", "qst_0428", "qst_0447"):
    print("===", qid, "===")
    for label, data in (("base", base.get(qid)), ("o1", o1.get(qid))):
        if not data:
            print(label, "missing")
            continue
        stages = data.get("retrieval_stages") or {}
        final = stages.get("final_before_generation") or {}
        print(label, "action=", data.get("route_action"),
              "final_docs=", final.get("document_ids", [])[:12],
              "final_chunks=", final.get("chunk_ids", [])[:12],
              "reserve=", data.get("original_candidate_reserve"))
        print(label, "selected_nodes=", (data.get("selected_nodes") or [])[:12],
              "missing_facets=", data.get("missing_facets"))
PY
