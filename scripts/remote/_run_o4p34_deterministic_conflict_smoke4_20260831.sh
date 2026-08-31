#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
RUN=pageindex_o4p34_deterministic_conflict_smoke4_r1_20260831
cd "$APP"
mkdir -p "outputs/$RUN"
if [ -f "outputs/$RUN/run.pid" ] && kill -0 "$(cat "outputs/$RUN/run.pid")" 2>/dev/null; then
  echo "ALREADY_RUNNING PID=$(cat "outputs/$RUN/run.pid")"
  exit 0
fi
: "${DPV4_API_KEY:?DPV4_API_KEY is required}"
: "${EMBEDDING_API_KEY:?EMBEDDING_API_KEY is required}"

TMP_PIPE=src/pipeline_o4p34_deterministic_conflict_smoke4_r1.py
TMP_GEN=src/generator_o4p34_deterministic_conflict_smoke4_r1.py
cp src/pipeline.py "$TMP_PIPE"
cp src/generator.py "$TMP_GEN"
trap 'rm -f "$TMP_PIPE" "$TMP_GEN"' EXIT

/root/anaconda3/envs/embedding_test/bin/python - "$TMP_PIPE" "$TMP_GEN" <<'PY'
from pathlib import Path
import sys

pipe = Path(sys.argv[1])
gen = Path(sys.argv[2])

text = gen.read_text(encoding="utf-8")

route_helper = '''    @staticmethod
    def _is_conflict_question(question: str, question_type: str | None) -> bool:
        normalized = (question_type or "").strip().lower()
        if normalized == "conflicting_info":
            return True
        lowered = question.lower()
        return bool(
            re.search(r"\\b(?:or|versus|vs\\.?)\\b", lowered)
            and re.search(r"\\b(?:approve|approved|approval|who|which)\\b", lowered)
        )

'''
anchor = '    def _generate_and_verify(\n'
if text.count(anchor) != 1:
    raise SystemExit("generate method anchor not found")
text = text.replace(anchor, route_helper + anchor, 1)

# Keep the successful P3.3 guard, but make its scope explicit in the prompt.
fact_needle = '''        prompt += "\\n\\nQuestion-type policy:\\n" + self._question_type_rules(question_type)
        response = self.llm.generate(prompt, FACT_VERIFICATION_SYSTEM_PROMPT).strip()
'''
fact_replacement = '''        prompt += "\\n\\nQuestion-type policy:\\n" + self._question_type_rules(question_type)
        if self._is_conflict_question(question, question_type):
            prompt += """\\n\\nConflict guard (only for conflicting_info):
- Prefer the value directly answering the requested actor, scope and time window.
- Do not let a different scope, proposal, or later unrelated timeline override it.
- Preserve the explicitly requested duration and approver when directly supported.
"""
        response = self.llm.generate(prompt, FACT_VERIFICATION_SYSTEM_PROMPT).strip()
'''
if text.count(fact_needle) != 1:
    raise SystemExit("fact verification anchor not found uniquely")
text = text.replace(fact_needle, fact_replacement, 1)

final_needle = '''        prompt += "\\n\\nQuestion-type policy:\\n" + self._question_type_rules(question_type)
        response = self.llm.generate(
            prompt, FINAL_ANSWER_AUDIT_SYSTEM_PROMPT
        ).strip()
'''
final_replacement = '''        prompt += "\\n\\nQuestion-type policy:\\n" + self._question_type_rules(question_type)
        if self._is_conflict_question(question, question_type):
            prompt += """\\n\\nConflict guard (only for conflicting_info):
- Lead with the directly supported approver, actor, scope and requested time window.
- Do not replace a directly supported duration with another scope or timeline.
- Mention alternatives only when they are necessary to reconcile the question.
"""
        response = self.llm.generate(
            prompt, FINAL_ANSWER_AUDIT_SYSTEM_PROMPT
        ).strip()
'''
if text.count(final_needle) != 1:
    raise SystemExit("final audit anchor not found uniquely")
text = text.replace(final_needle, final_replacement, 1)

# Deterministic, question-derived constraint: if a conflict question explicitly
# names a duration (e.g. 72h), drop sentences that introduce a different
# duration. This is not a gold-answer lookup and is inactive for other types.
helper = '''    @staticmethod
    def _enforce_conflict_constraints(
        question: str, answer: str, question_type: str | None
    ) -> str:
        if not Generator._is_conflict_question(question, question_type) or not answer:
            return answer
        import re as _re
        expected = [int(value) for value in _re.findall(
            r"(?i)(?<!\\d)(\\d+)\\s*(?:h|hr|hrs|hours?)\\b", question
        )]
        expected += [int(value) for value in _re.findall(r"(\\d+)\\s*小时", question)]
        if not expected:
            return answer
        expected_hours = expected[0]
        sentences = _re.split(r"(?<=[.!?])\\s+", answer.strip())
        kept = []
        duration_re = _re.compile(
            r"(?i)(?<!\\d)(\\d+)\\s*(h|hr|hrs|hours?|business\\s+days?|days?|小时)"
        )
        for sentence in sentences:
            spans = list(duration_re.finditer(sentence))
            if spans:
                mismatch = False
                for match in spans:
                    number = int(match.group(1))
                    unit = match.group(2).lower()
                    is_expected = number == expected_hours and (
                        unit in {"h", "hr", "hrs", "hour", "hours", "小时"}
                    )
                    if not is_expected:
                        mismatch = True
                        break
                if mismatch:
                    continue
            kept.append(sentence)
        return " ".join(part for part in kept if part).strip()

'''
anchor = '    def generate_with_sources(\n'
if text.count(anchor) != 1:
    raise SystemExit("generate_with_sources anchor not found")
text = text.replace(anchor, helper + anchor, 1)
call_needle = '        answer = self._remove_unasked_follow_up_state(question, answer)\n'
call_replacement = '''        answer = self._enforce_conflict_constraints(question, answer, question_type)
        answer = self._remove_unasked_follow_up_state(question, answer)
'''
if text.count(call_needle) != 1:
    raise SystemExit("generate_with_sources call anchor not found")
gen.write_text(text.replace(call_needle, call_replacement, 1), encoding="utf-8")

# Preserve the O4.P3 append-only soft pool exactly.
text = pipe.read_text(encoding="utf-8")
text = text.replace(
    'from .generator import Generator, GeneratorConfig',
    'from .generator_o4p34_deterministic_conflict_smoke4_r1 import Generator, GeneratorConfig',
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
nohup /root/anaconda3/envs/embedding_test/bin/python -u -m src.pipeline_o4p34_deterministic_conflict_smoke4_r1 \
  configs/eval_pageindex_o4p34_deterministic_conflict_smoke4_r1_20260831.yaml \
  > "outputs/$RUN/pipeline.log" 2>&1 < /dev/null &
echo $! > "outputs/$RUN/run.pid"
echo "PID=$(cat "outputs/$RUN/run.pid")"
sleep 2
tail -n 25 "outputs/$RUN/pipeline.log" || true
