"""Apply or rollback the isolated R11.B structured-query candidate union patch.

The patch is intentionally opt-in through ``retrieval.structured_query``.  It
adds one answer-free, question-derived structured representation and unions its
BM25/dense candidates with the original views at low weight.  A small reserve
of original-view chunks is retained before reranking so the experiment cannot
silently replace the baseline candidate set.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


SOURCE = Path("src/pipeline.py")
BACKUP = Path("src/pipeline.py.r11b_structured_query.bak")
MARKER = "structured_semantic_query"


FUNCTION_BLOCK = r'''
    def _structured_semantic_query(
        question: str, question_type: str | None
    ) -> tuple[str, dict] | None:
        """Build one answer-free structured retrieval representation.

        The model may only extract or lightly label terms already present in
        the question.  Unsupported values are discarded before the
        representation is used for retrieval; no gold answer or document ID
        is available to this function.
        """
        prompt = f"""Convert the enterprise search question below into one compact
structured retrieval representation. Do not answer it and do not guess any
missing value. Every concrete value in the JSON must be copied verbatim from
the question; generic field labels are allowed. Preserve entities, products,
systems, events, relationships, dates, quantities, status, region and other
hard constraints. Return JSON only with these arrays (empty arrays allowed):
{{"entities":[],"events":[],"constraints":[],"relations":[],"time":[]}}

Question type: {question_type or 'unknown'}
Question: {question}"""
        response = _get_rewrite_llm().generate(
            prompt,
            system_prompt=(
                "You are a conservative query-structure extractor. Never "
                "provide an answer. Output valid JSON only."
            ),
        ).strip()
        try:
            start, end = response.find("{"), response.rfind("}")
            payload = json.loads(response[start:end + 1])
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None

        question_tokens = {
            token.casefold()
            for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.:/%+@-]*", question)
        }
        allowed_fields = ("entities", "events", "constraints", "relations", "time")
        selected: dict[str, list[str]] = {}
        for field in allowed_fields:
            values = payload.get(field, [])
            if isinstance(values, str):
                values = [values]
            if not isinstance(values, list):
                continue
            kept: list[str] = []
            for value in values:
                if not isinstance(value, str):
                    continue
                value = value.strip()
                if len(value) < 2:
                    continue
                value_tokens = {
                    token.casefold()
                    for token in re.findall(
                        r"[A-Za-z0-9][A-Za-z0-9_.:/%+@-]*", value
                    )
                }
                if not value_tokens:
                    continue
                overlap = len(value_tokens & question_tokens) / len(value_tokens)
                if overlap < 0.5:
                    continue
                if value not in kept:
                    kept.append(value)
            if kept:
                selected[field] = kept[:4]

        if not selected:
            return None
        parts = [
            f"{field}: {', '.join(values)}"
            for field in allowed_fields
            if (values := selected.get(field))
        ]
        representation = "; ".join(parts).strip()
        if len(representation) < 8:
            return None
        return representation, selected
'''


DECLARATIONS = '''        structured_query_trace: dict = {}
        structured_original_result_lists: list[list] = []
'''


STRUCTURED_BLOCK = r'''
            structured_query_cfg = retrieval_cfg.get("structured_query", {})
            if (
                structured_query_cfg.get("enabled", False)
                and retrieval_type_key in structured_query_cfg.get(
                    "types", ["semantic"]
                )
            ):
                try:
                    structured = _structured_semantic_query(query, retrieval_type_key)
                    if structured:
                        structured_text, structured_fields = structured
                        structured_query_trace = {
                            "representation": structured_text,
                            "fields": structured_fields,
                            "views": [],
                        }
                        per_doc_limit = max(
                            1,
                            int(
                                structured_query_cfg.get(
                                    "max_chunks_per_doc", 3
                                )
                            ),
                        )
                        for view_name, view_kind, default_weight in (
                            (
                                "structured_keyword",
                                "keyword",
                                0.22,
                            ),
                            ("structured_dense", "dense", 0.22),
                        ):
                            value = retrieve_view(structured_text, view_kind)
                            per_doc: dict[str, int] = {}
                            limited: list = []
                            for item in value:
                                doc_id = getattr(item, "doc_id", "")
                                if per_doc.get(doc_id, 0) >= per_doc_limit:
                                    continue
                                per_doc[doc_id] = per_doc.get(doc_id, 0) + 1
                                limited.append(item)
                            add_view(
                                view_name,
                                limited,
                                float(
                                    structured_query_cfg.get(
                                        f"{view_kind}_weight", default_weight
                                    )
                                ),
                            )
                            structured_query_trace["views"].append({
                                "view": view_name,
                                "selected_chunks": len(limited),
                                "selected_documents": len(per_doc),
                            })
                        print(
                            f"  [structured_query] {qid}: one representation, "
                            f"{len(structured_query_trace['views'])} views added"
                        )
                except Exception as exc:  # structured view is best-effort
                    structured_query_trace = {"error": str(exc)}
                    print(f"  [structured_query] skipped {qid}: {exc}")

'''


RESERVE_BLOCK = r'''
        if (
            structured_query_trace
            and structured_original_result_lists
            and result_lists
        ):
            reserve_n = max(
                0,
                int(
                    structured_query_cfg.get(
                        "original_reserve_chunks", 12
                    )
                ),
            )
            if reserve_n:
                original_items: list = []
                original_ids: set[str] = set()
                for original_list in structured_original_result_lists:
                    for item in original_list:
                        if item.chunk_id in original_ids:
                            continue
                        original_ids.add(item.chunk_id)
                        original_items.append(item)
                selected: list = []
                selected_ids: set[str] = set()
                for item in results:
                    if item.chunk_id in original_ids and len(selected) < reserve_n:
                        selected.append(item)
                        selected_ids.add(item.chunk_id)
                for item in original_items:
                    if len(selected) >= reserve_n:
                        break
                    if item.chunk_id not in selected_ids:
                        selected.append(item)
                        selected_ids.add(item.chunk_id)
                for item in results:
                    if len(selected) >= retrieval_result_count:
                        break
                    if item.chunk_id not in selected_ids:
                        selected.append(item)
                        selected_ids.add(item.chunk_id)
                results = selected[:retrieval_result_count]
                structured_query_trace["original_reserve_chunks"] = sum(
                    item.chunk_id in original_ids for item in results
                )

'''


def apply() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    if MARKER in text:
        print("R11B_ALREADY_APPLIED")
        return
    shutil.copy2(SOURCE, BACKUP)

    needle = '    def _answer_intent_queries(\n'
    if needle not in text:
        shutil.copy2(BACKUP, SOURCE)
        raise RuntimeError("structured query function anchor not found")
    text = text.replace(needle, FUNCTION_BLOCK + "\n" + needle, 1)

    needle = '        semantic_docfirst_trace: dict = {}\n'
    if needle not in text:
        shutil.copy2(BACKUP, SOURCE)
        raise RuntimeError("trace declaration anchor not found")
    text = text.replace(needle, needle + DECLARATIONS, 1)

    needle = '            result_lists: list[list] = []\n            route_weights: list[float] = []\n'
    replacement = (
        '            result_lists: list[list] = []\n'
        '            route_weights: list[float] = []\n'
    )
    if needle not in text:
        shutil.copy2(BACKUP, SOURCE)
        raise RuntimeError("result-list anchor not found")
    text = text.replace(needle, replacement, 1)

    replacements = [
        (
            '                keyword_results = retrieve_view(query, "keyword")\n',
            '                keyword_results = retrieve_view(query, "keyword")\n'
            '                structured_original_result_lists.append(keyword_results)\n',
        ),
        (
            '            if "original_dense" in views:\n                add_view(\n                    "original_dense",\n                    retrieve_view(query, "dense"),\n',
            '            if "original_dense" in views:\n'
            '                dense_results = retrieve_view(query, "dense")\n'
            '                structured_original_result_lists.append(dense_results)\n'
            '                add_view(\n                    "original_dense",\n                    dense_results,\n',
        ),
    ]
    for old, new in replacements:
        if old not in text:
            shutil.copy2(BACKUP, SOURCE)
            raise RuntimeError("original-view anchor not found")
        text = text.replace(old, new, 1)

    needle = '            results = _rrf_merge(\n'
    if needle not in text:
        shutil.copy2(BACKUP, SOURCE)
        raise RuntimeError("RRF anchor not found")
    text = text.replace(needle, STRUCTURED_BLOCK + needle, 1)

    needle = '        def retrieve_query(value: str) -> list:\n'
    if needle not in text:
        shutil.copy2(BACKUP, SOURCE)
        raise RuntimeError("reserve insertion anchor not found")
    text = text.replace(needle, RESERVE_BLOCK + needle, 1)

    needle = '        if semantic_anchor_trace:\n            route_trace["semantic_anchor_rescue"] = semantic_anchor_trace\n'
    replacement = needle + '        if structured_query_trace:\n            route_trace["structured_semantic_query"] = structured_query_trace\n'
    if needle not in text:
        shutil.copy2(BACKUP, SOURCE)
        raise RuntimeError("route trace anchor not found")
    text = text.replace(needle, replacement, 1)

    SOURCE.write_text(text, encoding="utf-8")
    print("R11B_APPLIED")


def rollback() -> None:
    if BACKUP.exists():
        shutil.copy2(BACKUP, SOURCE)
        BACKUP.unlink()
        print("R11B_ROLLED_BACK")
    else:
        print("R11B_NO_BACKUP")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "apply"
    if action == "apply":
        apply()
    elif action == "rollback":
        rollback()
    else:
        raise SystemExit("usage: apply_r11b_structured_query_union.py [apply|rollback]")
