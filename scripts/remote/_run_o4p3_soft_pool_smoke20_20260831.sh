#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
RUN=pageindex_o4p3_soft_pool_smoke20_20260831
cd "$APP"
mkdir -p "outputs/$RUN"
if [ -f "outputs/$RUN/run.pid" ] && kill -0 "$(cat "outputs/$RUN/run.pid")" 2>/dev/null; then
  echo "ALREADY_RUNNING PID=$(cat "outputs/$RUN/run.pid")"
  exit 0
fi
: "${DPV4_API_KEY:?DPV4_API_KEY is required}"
: "${EMBEDDING_API_KEY:?EMBEDDING_API_KEY is required}"

TMP_MODULE=src/pipeline_o4p3_smoke.py
cp src/pipeline.py "$TMP_MODULE"
trap 'rm -f "$TMP_MODULE"' EXIT

/root/anaconda3/envs/embedding_test/bin/python - "$TMP_MODULE" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
needle = '        semantic_anchor_cfg = retrieval_cfg.get("semantic_anchor_rescue", {})\n'
replacement = '''        rerank_after_results = list(results)\n\n        semantic_anchor_cfg = retrieval_cfg.get("semantic_anchor_rescue", {})\n'''
if needle not in text:
    raise SystemExit("O4.P3 insertion point (rerank) not found")
text = text.replace(needle, replacement, 1)

needle = '        retrieval_stage_trace["final_before_generation"] = summarize_results(results)\n'
block = '''        document_soft_pool_cfg = retrieval_cfg.get("document_soft_pool", {})\n        if (\n            document_soft_pool_cfg.get("enabled", False)\n            and (\n                not document_soft_pool_cfg.get("types")\n                or retrieval_type_key in document_soft_pool_cfg.get("types", [])\n            )\n        ):\n            try:\n                max_extra_docs = max(0, int(document_soft_pool_cfg.get("max_extra_docs", 2)))\n                max_chunks_per_doc = max(1, int(document_soft_pool_cfg.get("max_chunks_per_doc", 1)))\n                insertion_after = max(0, int(document_soft_pool_cfg.get("insertion_after_chunks", 8)))\n                existing_chunks = {item.chunk_id for item in results}\n                existing_docs = {item.doc_id for item in results if item.doc_id}\n                added_items = []\n                added_docs = []\n                per_doc = {}\n                for item in rerank_after_results:\n                    if item.chunk_id in existing_chunks or not item.doc_id or item.doc_id in existing_docs:\n                        continue\n                    if per_doc.get(item.doc_id, 0) >= max_chunks_per_doc:\n                        continue\n                    added_items.append(item)\n                    added_docs.append(item.doc_id)\n                    per_doc[item.doc_id] = per_doc.get(item.doc_id, 0) + 1\n                    existing_chunks.add(item.chunk_id)\n                    existing_docs.add(item.doc_id)\n                    if len(added_docs) >= max_extra_docs:\n                        break\n                if added_items:\n                    split = min(insertion_after, len(results))\n                    results = results[:split] + added_items + results[split:]\n                retrieval_stage_trace["document_soft_pool"] = {\n                    "enabled": True,\n                    "max_extra_docs": max_extra_docs,\n                    "max_chunks_per_doc": max_chunks_per_doc,\n                    "insertion_after_chunks": insertion_after,\n                    "added_document_ids": added_docs,\n                    "added_chunk_ids": [item.chunk_id for item in added_items],\n                    "baseline_document_count": len(existing_docs) - len(added_docs),\n                    "final_document_count": len(existing_docs),\n                }\n            except Exception as exc:\n                retrieval_stage_trace["document_soft_pool"] = {"enabled": True, "error": str(exc)}\n                print(f"  [document_soft_pool] skipped {qid}: {exc}")\n\n        retrieval_stage_trace["final_before_generation"] = summarize_results(results)\n'''
if needle not in text:
    raise SystemExit("O4.P3 insertion point (final) not found")
text = text.replace(needle, block, 1)
path.write_text(text, encoding="utf-8")
PY

export TRANSFORMERS_OFFLINE=1
export QUESTION_PARALLELISM=4
nohup /root/anaconda3/envs/embedding_test/bin/python -u -m src.pipeline_o4p3_smoke \
  configs/eval_pageindex_o4p3_soft_pool_smoke20_20260831.yaml \
  > "outputs/$RUN/pipeline.log" 2>&1 < /dev/null &
echo $! > "outputs/$RUN/run.pid"
echo "PID=$(cat "outputs/$RUN/run.pid")"
sleep 2
tail -n 25 "outputs/$RUN/pipeline.log" || true
