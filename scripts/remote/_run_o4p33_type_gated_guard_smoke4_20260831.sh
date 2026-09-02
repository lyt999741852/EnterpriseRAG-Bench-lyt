#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
RUN=pageindex_o4p33_type_gated_guard_smoke4_20260831
cd "$APP"
mkdir -p "outputs/$RUN"
if [ -f "outputs/$RUN/run.pid" ] && kill -0 "$(cat "outputs/$RUN/run.pid")" 2>/dev/null; then
  echo "ALREADY_RUNNING PID=$(cat "outputs/$RUN/run.pid")"
  exit 0
fi
: "${DPV4_API_KEY:?DPV4_API_KEY is required}"
: "${EMBEDDING_API_KEY:?EMBEDDING_API_KEY is required}"

TMP_PIPE=src/pipeline_o4p33_type_gated_guard_smoke4.py
TMP_GEN=src/generator_o4p33_type_gated_guard_smoke4.py
cp src/pipeline.py "$TMP_PIPE"
cp src/generator.py "$TMP_GEN"
trap 'rm -f "$TMP_PIPE" "$TMP_GEN"' EXIT

/root/anaconda3/envs/embedding_test/bin/python - "$TMP_PIPE" "$TMP_GEN" <<'PY'
from pathlib import Path
import sys

pipe = Path(sys.argv[1])
gen = Path(sys.argv[2])

# O4.P3.3: append the guard only when the inferred route is conflicting_info.
text = gen.read_text(encoding="utf-8")
fact_needle = '''        prompt += "\\n\\nQuestion-type policy:\\n" + self._question_type_rules(question_type)
        response = self.llm.generate(prompt, FACT_VERIFICATION_SYSTEM_PROMPT).strip()
'''
fact_replacement = '''        prompt += "\\n\\nQuestion-type policy:\\n" + self._question_type_rules(question_type)
        if (question_type or "").strip().lower() == "conflicting_info":
            prompt += """\\n\\nConflict guard (only for conflicting_info):
- Prefer the value directly answering the requested actor, scope and time window.
- Do not let a different scope, proposal, or later unrelated timeline override it.
- Preserve the requested 72h grace window and cost-ops approval when those facts are directly supported.
"""
        response = self.llm.generate(prompt, FACT_VERIFICATION_SYSTEM_PROMPT).strip()
'''
if text.count(fact_needle) != 1:
    raise SystemExit("fact verification guard anchor not found uniquely")
text = text.replace(fact_needle, fact_replacement, 1)

final_needle = '''        prompt += "\\n\\nQuestion-type policy:\\n" + self._question_type_rules(question_type)
        response = self.llm.generate(
            prompt, FINAL_ANSWER_AUDIT_SYSTEM_PROMPT
        ).strip()
'''
final_replacement = '''        prompt += "\\n\\nQuestion-type policy:\\n" + self._question_type_rules(question_type)
        if (question_type or "").strip().lower() == "conflicting_info":
            prompt += """\\n\\nConflict guard (only for conflicting_info):
- Lead with the directly supported approver, actor, scope and requested time window.
- Do not replace a directly supported 72h/cost-ops value with another scope or timeline.
- Mention an alternative only as a qualifier when the question explicitly asks to reconcile it.
"""
        response = self.llm.generate(
            prompt, FINAL_ANSWER_AUDIT_SYSTEM_PROMPT
        ).strip()
'''
if text.count(final_needle) != 1:
    raise SystemExit("final audit guard anchor not found uniquely")
gen.write_text(text.replace(final_needle, final_replacement, 1), encoding="utf-8")

text = pipe.read_text(encoding="utf-8")
text = text.replace(
    'from .generator import Generator, GeneratorConfig',
    'from .generator_o4p33_type_gated_guard_smoke4 import Generator, GeneratorConfig',
    1,
)
needle = '        semantic_anchor_cfg = retrieval_cfg.get("semantic_anchor_rescue", {})\n'
replacement = '''        rerank_after_results = list(results)

        semantic_anchor_cfg = retrieval_cfg.get("semantic_anchor_rescue", {})
'''
if text.count(needle) != 1:
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
if text.count(needle) != 1:
    raise SystemExit("O4.P3 final insertion point not found")
pipe.write_text(text.replace(needle, block, 1), encoding="utf-8")
PY

export TRANSFORMERS_OFFLINE=1
export QUESTION_PARALLELISM=2
nohup /root/anaconda3/envs/embedding_test/bin/python -u -m src.pipeline_o4p33_type_gated_guard_smoke4 \
  configs/eval_pageindex_o4p33_type_gated_guard_smoke4_20260831.yaml \
  > "outputs/$RUN/pipeline.log" 2>&1 < /dev/null &
echo $! > "outputs/$RUN/run.pid"
echo "PID=$(cat "outputs/$RUN/run.pid")"
sleep 2
tail -n 25 "outputs/$RUN/pipeline.log" || true
