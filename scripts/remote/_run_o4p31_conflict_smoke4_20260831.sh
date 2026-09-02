#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
RUN=pageindex_o4p31_conflict_smoke4_20260831
cd "$APP"
mkdir -p "outputs/$RUN"
if [ -f "outputs/$RUN/run.pid" ] && kill -0 "$(cat "outputs/$RUN/run.pid")" 2>/dev/null; then
  echo "ALREADY_RUNNING PID=$(cat "outputs/$RUN/run.pid")"
  exit 0
fi
: "${DPV4_API_KEY:?DPV4_API_KEY is required}"
: "${EMBEDDING_API_KEY:?EMBEDDING_API_KEY is required}"

TMP_PIPE=src/pipeline_o4p31_conflict_smoke4.py
TMP_GEN=src/generator_o4p31_conflict_smoke4.py
cp src/pipeline.py "$TMP_PIPE"
cp src/generator.py "$TMP_GEN"
trap 'rm -f "$TMP_PIPE" "$TMP_GEN"' EXIT

/root/anaconda3/envs/embedding_test/bin/python - "$TMP_PIPE" "$TMP_GEN" <<'PY'
from pathlib import Path
import sys

pipe = Path(sys.argv[1])
gen = Path(sys.argv[2])

text = gen.read_text(encoding="utf-8")
needle = '  "conflicts": []\n}}\n'
replacement = '''  "conflicts": [],
  "resolved_conflicts": []
}}

Conflict reporting contract:
- `conflicts` is a blocking field. Put only contradictions that remain unresolved after
  applying explicit final/current/canonical/applicable-source precedence in `conflicts`.
- When an accepted passage is explicitly final, current, canonical, or otherwise applicable
  and competing passages are older, draft, or differently scoped, record those resolved
  discrepancies in `resolved_conflicts`, not in `conflicts`.
- If two contradictory passages have equal authority/status and no explicit precedence resolves
  them, keep the contradiction in `conflicts`, set coverage_complete=false, and do not admit
  either concrete conflicting value as an answer fact.
- Never set coverage_complete=true while blocking `conflicts` is non-empty.
- Return `resolved_conflicts` as a JSON list in addition to the existing fields.
'''
if needle not in text:
    raise SystemExit("conflict selector template anchor not found")
gen.write_text(text.replace(needle, replacement, 1), encoding="utf-8")

text = pipe.read_text(encoding="utf-8")
text = text.replace(
    'from .generator import Generator, GeneratorConfig',
    'from .generator_o4p31_conflict_smoke4 import Generator, GeneratorConfig',
    1,
)
needle = '        semantic_anchor_cfg = retrieval_cfg.get("semantic_anchor_rescue", {})\n'
replacement = '''        rerank_after_results = list(results)

        semantic_anchor_cfg = retrieval_cfg.get("semantic_anchor_rescue", {})
'''
if needle not in text:
    raise SystemExit("O4.P3 rerank insertion point not found")
text = text.replace(needle, replacement, 1)

needle = '        retrieval_stage_trace["final_before_generation"] = summarize_results(results)\n'
block = '''        document_soft_pool_cfg = retrieval_cfg.get("document_soft_pool", {})
        if (
            document_soft_pool_cfg.get("enabled", False)
            and (
                not document_soft_pool_cfg.get("types")
                or retrieval_type_key in document_soft_pool_cfg.get("types", [])
            )
        ):
            max_extra_docs = max(0, int(document_soft_pool_cfg.get("max_extra_docs", 2)))
            max_chunks_per_doc = max(1, int(document_soft_pool_cfg.get("max_chunks_per_doc", 1)))
            insertion_after = max(0, int(document_soft_pool_cfg.get("insertion_after_chunks", 8)))
            existing_chunks = {item.chunk_id for item in results}
            existing_docs = {item.doc_id for item in results if item.doc_id}
            added_items = []
            added_docs = []
            per_doc = {}
            for item in rerank_after_results:
                if item.chunk_id in existing_chunks or not item.doc_id or item.doc_id in existing_docs:
                    continue
                if per_doc.get(item.doc_id, 0) >= max_chunks_per_doc:
                    continue
                added_items.append(item)
                added_docs.append(item.doc_id)
                per_doc[item.doc_id] = per_doc.get(item.doc_id, 0) + 1
                existing_chunks.add(item.chunk_id)
                existing_docs.add(item.doc_id)
                if len(added_docs) >= max_extra_docs:
                    break
            if added_items:
                split = min(insertion_after, len(results))
                results = results[:split] + added_items + results[split:]
            retrieval_stage_trace["document_soft_pool"] = {
                "enabled": True,
                "max_extra_docs": max_extra_docs,
                "max_chunks_per_doc": max_chunks_per_doc,
                "insertion_after_chunks": insertion_after,
                "added_document_ids": added_docs,
                "added_chunk_ids": [item.chunk_id for item in added_items],
            }

        retrieval_stage_trace["final_before_generation"] = summarize_results(results)
'''
if needle not in text:
    raise SystemExit("O4.P3 final insertion point not found")
pipe.write_text(text.replace(needle, block, 1), encoding="utf-8")
PY

export TRANSFORMERS_OFFLINE=1
export QUESTION_PARALLELISM=2
nohup /root/anaconda3/envs/embedding_test/bin/python -u -m src.pipeline_o4p31_conflict_smoke4 \
  configs/eval_pageindex_o4p31_conflict_smoke4_20260831.yaml \
  > "outputs/$RUN/pipeline.log" 2>&1 < /dev/null &
echo $! > "outputs/$RUN/run.pid"
echo "PID=$(cat "outputs/$RUN/run.pid")"
sleep 2
tail -n 25 "outputs/$RUN/pipeline.log" || true
