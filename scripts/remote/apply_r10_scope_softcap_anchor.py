"""Apply or rollback the temporary R10 retrieval scope/soft-quota smoke patch."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


SOURCE = Path("src/pipeline.py")
BACKUP = Path("src/pipeline.py.r10_scope_softcap_anchor.bak")
MARKER = "r10_soft_document_quota"

RESCUE_OLD = """        if semantic_rescue_cfg.get("enabled", False) and reranker_enabled:\n"""
RESCUE_NEW = """        if (\n            semantic_rescue_cfg.get("enabled", False)\n            and reranker_enabled\n            and (\n                not semantic_rescue_cfg.get("types")\n                or retrieval_type_key in semantic_rescue_cfg.get("types", [])\n            )\n        ):\n"""

LEXICAL_BLOCK = r'''
            lexical_variant_cfg = retrieval_cfg.get("lexical_anchor_variants", {})
            if (
                lexical_variant_cfg.get("enabled", False)
                and retrieval_type_key in lexical_variant_cfg.get("types", ["semantic"])
            ):
                stop_tokens = {
                    "about", "after", "also", "been", "being", "between",
                    "could", "does", "from", "have", "into", "more", "most",
                    "other", "over", "should", "some", "than", "that", "their",
                    "there", "these", "they", "this", "those", "through", "under",
                    "what", "when", "where", "which", "while", "with", "would",
                    "your", "explain", "describe", "please", "system", "company",
                    "document", "documents", "question", "following", "according",
                }
                variant_tokens: list[str] = []
                for token in re.findall(r"[A-Za-z][A-Za-z0-9_.:/-]{2,}", query):
                    low = token.lower().strip("._:/-")
                    if low in stop_tokens or low in {item.lower() for item in variant_tokens}:
                        continue
                    if any(ch.isdigit() for ch in token) or token.isupper() or len(token) >= 6:
                        variant_tokens.append(token)
                variant_tokens = sorted(
                    variant_tokens,
                    key=lambda item: (-len(item), query.lower().find(item.lower())),
                )[: max(2, int(lexical_variant_cfg.get("token_limit", 10)))]
                pairs = list(itertools.combinations(variant_tokens, 2))[: max(0, int(lexical_variant_cfg.get("max_pair_queries", 16)))]
                pair_weight = float(lexical_variant_cfg.get("weight", 0.2))
                pair_trace: list[dict] = []
                for left, right in pairs:
                    pair_results = retrieve_view(f"{left} {right}", "keyword")
                    max_per_doc = max(1, int(lexical_variant_cfg.get("max_chunks_per_doc", 2)))
                    per_doc: dict[str, int] = {}
                    limited_results: list = []
                    for item in pair_results:
                        doc_id = getattr(item, "doc_id", "")
                        if per_doc.get(doc_id, 0) >= max_per_doc:
                            continue
                        per_doc[doc_id] = per_doc.get(doc_id, 0) + 1
                        limited_results.append(item)
                    add_view("lexical_anchor_keyword", limited_results, pair_weight)
                    pair_trace.append({"query": f"{left} {right}", "selected_chunks": len(limited_results)})
                print(f"  [lexical_anchor_variants] {qid}: {len(pairs)} pair query(s) added")
                semantic_anchor_trace["variant_tokens"] = variant_tokens
                semantic_anchor_trace["variant_pairs"] = pair_trace
'''

SOFT_NEEDLE = '        expansion_cfg = retrieval_cfg.get("parent_expansion", {})\n'
SOFT_BLOCK = r'''        r10_soft_cfg = retrieval_cfg.get("r10_soft_document_quota", {})
        r10_soft_trace: dict = {}
        if r10_soft_cfg.get("enabled", False):
            # Soft document quota: retain the first evidence from every
            # document, then fill remaining slots in rank order. There is no
            # global hard total cap, so multi-hop documents are not discarded.
            max_per_doc = max(1, int(r10_soft_cfg.get("max_chunks_per_doc", 2)))
            before = summarize_results(results)
            ordered_docs: list[str] = []
            by_doc: dict[str, list] = {}
            for item in results:
                if item.doc_id not in by_doc:
                    ordered_docs.append(item.doc_id)
                    by_doc[item.doc_id] = []
                by_doc[item.doc_id].append(item)
            limited: list = []
            used: dict[str, int] = {}
            if r10_soft_cfg.get("preserve_one_per_document", True):
                for doc_id in ordered_docs:
                    item = by_doc[doc_id][0]
                    limited.append(item)
                    used[doc_id] = 1
            for item in results:
                if item in limited:
                    continue
                if used.get(item.doc_id, 0) >= max_per_doc:
                    continue
                limited.append(item)
                used[item.doc_id] = used.get(item.doc_id, 0) + 1
            results = limited
            r10_soft_trace = {
                "max_chunks_per_doc": max_per_doc,
                "preserve_one_per_document": bool(r10_soft_cfg.get("preserve_one_per_document", True)),
                "before": before,
                "after": summarize_results(results),
            }
'''

TRACE_NEEDLE = "        if semantic_docfirst_trace:\n            route_trace[\"semantic_document_first\"] = semantic_docfirst_trace\n"
TRACE_BLOCK = TRACE_NEEDLE + "        if r10_soft_trace:\n            route_trace[\"r10_soft_document_quota\"] = r10_soft_trace\n"


def apply() -> None:
    original = SOURCE.read_text(encoding="utf-8")
    if MARKER in original:
        print("R10_SCOPE_SOFTCAP_ALREADY_APPLIED")
        return
    for needle in (RESCUE_OLD, SOFT_NEEDLE, TRACE_NEEDLE):
        if needle not in original:
            raise RuntimeError(f"R10 insertion point not found: {needle[:60]}")
    shutil.copy2(SOURCE, BACKUP)
    patched = original.replace(RESCUE_OLD, RESCUE_NEW, 1)
    patched = patched.replace("import hashlib\nimport re", "import hashlib\nimport itertools\nimport re", 1)
    lexical_needle = '                )\n            if "original_dense" in views:\n'
    if lexical_needle not in patched:
        shutil.copy2(BACKUP, SOURCE)
        raise RuntimeError("R10 lexical insertion point not found")
    patched = patched.replace(lexical_needle, "                )\n" + LEXICAL_BLOCK + '            if "original_dense" in views:\n', 1)
    patched = patched.replace(SOFT_NEEDLE, SOFT_BLOCK + SOFT_NEEDLE, 1)
    patched = patched.replace(TRACE_NEEDLE, TRACE_BLOCK, 1)
    SOURCE.write_text(patched, encoding="utf-8")
    print("R10_SCOPE_SOFTCAP_APPLIED")


def rollback() -> None:
    if BACKUP.exists():
        shutil.copy2(BACKUP, SOURCE)
        BACKUP.unlink()
        print("R10_SCOPE_SOFTCAP_ROLLED_BACK")
    else:
        print("R10_SCOPE_SOFTCAP_NO_BACKUP")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "apply"
    if action == "apply":
        apply()
    elif action == "rollback":
        rollback()
    else:
        raise SystemExit("usage: apply_r10_scope_softcap_anchor.py [apply|rollback]")
