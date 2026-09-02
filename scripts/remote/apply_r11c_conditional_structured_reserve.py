"""Layer a conditional trigger and bounded candidate reserve on the R11.B patch."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

SOURCE = Path("src/pipeline.py")
BACKUP = Path("src/pipeline.py.r11c_conditional_structured_reserve.bak")
MARKER = "conditional_structured_query_trigger"

TRIGGER_BLOCK = (
    '            # conditional_structured_query_trigger\n'
    '            # Trigger only when original keyword/dense views disagree.\n'
    '            agreement_top_n = max(1, int(structured_query_cfg.get("agreement_top_docs", 8)))\n'
    '            min_shared_docs = max(0, int(structured_query_cfg.get("min_shared_docs", 1)))\n'
    '            def _ordered_doc_ids(items: list) -> list[str]:\n'
    '                ids: list[str] = []\n'
    '                seen: set[str] = set()\n'
    '                for item in items:\n'
    '                    doc_id = getattr(item, "doc_id", "")\n'
    '                    if doc_id and doc_id not in seen:\n'
    '                        seen.add(doc_id)\n'
    '                        ids.append(doc_id)\n'
    '                    if len(ids) >= agreement_top_n:\n'
    '                        break\n'
    '                return ids\n'
    '            original_top_docs = [_ordered_doc_ids(items) for items in structured_original_result_lists]\n'
    '            shared_original_docs = (set(original_top_docs[0]) & set(original_top_docs[1])\n'
    '                if len(original_top_docs) >= 2 else set())\n'
    '            structured_low_agreement = len(shared_original_docs) < min_shared_docs\n'
)


def apply() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    if MARKER in text:
        print("R11C_ALREADY_APPLIED")
        return
    if "structured_semantic_query" not in text:
        raise RuntimeError("R11.B patch must be applied first")
    shutil.copy2(SOURCE, BACKUP)
    needle = '            structured_query_cfg = retrieval_cfg.get("structured_query", {})\n'
    if needle not in text:
        shutil.copy2(BACKUP, SOURCE)
        raise RuntimeError("structured query config anchor not found")
    text = text.replace(needle, needle + TRIGGER_BLOCK, 1)
    old = ('                structured_query_cfg.get("enabled", False)\n'
           '                and retrieval_type_key in structured_query_cfg.get(\n'
           '                    "types", ["semantic"]\n'
           '                )\n')
    new = old + '                and structured_low_agreement\n'
    if old not in text:
        shutil.copy2(BACKUP, SOURCE)
        raise RuntimeError("structured query condition anchor not found")
    text = text.replace(old, new, 1)
    old = '                            value = retrieve_view(structured_text, view_kind)\n'
    new = old + ('                            value = value[:max(1, int(structured_query_cfg.get("candidate_top_n", 40)))]\n')
    if old not in text:
        shutil.copy2(BACKUP, SOURCE)
        raise RuntimeError("structured candidate anchor not found")
    text = text.replace(old, new, 1)
    old = '                            "views": [],\n'
    new = old + ('                            "trigger": {"low_agreement": structured_low_agreement, "agreement_top_docs": agreement_top_n, "min_shared_docs": min_shared_docs, "shared_documents": sorted(shared_original_docs), "original_top_documents": original_top_docs},\n')
    if old not in text:
        shutil.copy2(BACKUP, SOURCE)
        raise RuntimeError("structured trace anchor not found")
    text = text.replace(old, new, 1)
    SOURCE.write_text(text, encoding="utf-8")
    print("R11C_APPLIED")


def rollback() -> None:
    if BACKUP.exists():
        shutil.copy2(BACKUP, SOURCE)
        BACKUP.unlink()
        print("R11C_ROLLED_BACK")
    else:
        print("R11C_NO_BACKUP")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "apply"
    if action == "apply":
        apply()
    elif action == "rollback":
        rollback()
    else:
        raise SystemExit("usage: apply_r11c_conditional_structured_reserve.py [apply|rollback]")
