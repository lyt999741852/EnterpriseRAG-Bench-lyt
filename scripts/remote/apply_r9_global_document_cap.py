"""Apply or rollback the R9 global document/chunk cap smoke patch."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


SOURCE = Path("src/pipeline.py")
BACKUP = Path("src/pipeline.py.r9_global_document_cap.bak")
MARKER = "r9_global_document_cap"

INIT_NEEDLE = "        semantic_docfirst_trace: dict = {}\n"
INIT_BLOCK = INIT_NEEDLE + "        r9_global_cap_trace: dict = {}\n"

CAP_NEEDLE = "        expansion_cfg = retrieval_cfg.get(\"parent_expansion\", {})\n"
CAP_BLOCK = r'''        r9_cap_cfg = retrieval_cfg.get("r9_global_document_cap", {})
        if r9_cap_cfg.get("enabled", False):
            # Apply one global cap after all retrieval branches have merged.
            # This complements per-query quotas and prevents many facet views
            # from multiplying the same document's contribution.
            max_chunks_per_doc = max(
                1, int(r9_cap_cfg.get("max_chunks_per_doc", 2))
            )
            max_total_chunks = max(
                1, int(r9_cap_cfg.get("max_total_chunks", rerank_top_n))
            )
            before = summarize_results(results)
            per_doc: dict[str, int] = {}
            limited: list = []
            for item in results:
                doc_id = getattr(item, "doc_id", "")
                if per_doc.get(doc_id, 0) >= max_chunks_per_doc:
                    continue
                per_doc[doc_id] = per_doc.get(doc_id, 0) + 1
                limited.append(item)
                if len(limited) >= max_total_chunks:
                    break
            results = limited
            r9_global_cap_trace = {
                "max_chunks_per_doc": max_chunks_per_doc,
                "max_total_chunks": max_total_chunks,
                "before": before,
                "after": summarize_results(results),
            }
'''

TRACE_NEEDLE = "        if semantic_docfirst_trace:\n            route_trace[\"semantic_document_first\"] = semantic_docfirst_trace\n"
TRACE_BLOCK = TRACE_NEEDLE + "        if r9_global_cap_trace:\n            route_trace[\"r9_global_document_cap\"] = r9_global_cap_trace\n"


def apply() -> None:
    original = SOURCE.read_text(encoding="utf-8")
    if MARKER in original:
        print("R9_GLOBAL_DOCUMENT_CAP_ALREADY_APPLIED")
        return
    if INIT_NEEDLE not in original or CAP_NEEDLE not in original or TRACE_NEEDLE not in original:
        raise RuntimeError("R9 insertion point not found")
    shutil.copy2(SOURCE, BACKUP)
    patched = original.replace(INIT_NEEDLE, INIT_BLOCK, 1)
    patched = patched.replace(CAP_NEEDLE, CAP_BLOCK + CAP_NEEDLE, 1)
    patched = patched.replace(TRACE_NEEDLE, TRACE_BLOCK, 1)
    SOURCE.write_text(patched, encoding="utf-8")
    print("R9_GLOBAL_DOCUMENT_CAP_APPLIED")


def rollback() -> None:
    if BACKUP.exists():
        shutil.copy2(BACKUP, SOURCE)
        BACKUP.unlink()
        print("R9_GLOBAL_DOCUMENT_CAP_ROLLED_BACK")
    else:
        print("R9_GLOBAL_DOCUMENT_CAP_NO_BACKUP")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "apply"
    if action == "apply":
        apply()
    elif action == "rollback":
        rollback()
    else:
        raise SystemExit("usage: apply_r9_global_document_cap.py [apply|rollback]")
