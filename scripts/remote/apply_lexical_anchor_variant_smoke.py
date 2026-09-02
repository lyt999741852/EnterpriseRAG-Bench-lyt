"""Apply or rollback the opt-in lexical-anchor-pair smoke patch."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

SOURCE = Path("src/pipeline.py")
BACKUP = Path("src/pipeline.py.lexical_anchor_variant_smoke.bak")
MARKER = "lexical_anchor_variants"

BLOCK = r'''
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
                )[: max(2, int(lexical_variant_cfg.get("token_limit", 8)))]
                pairs = list(itertools.combinations(variant_tokens, 2))[: max(0, int(lexical_variant_cfg.get("max_pair_queries", 20)))]
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


def apply() -> None:
    original = SOURCE.read_text(encoding="utf-8")
    if MARKER in original:
        print("LEXICAL_ANCHOR_VARIANT_ALREADY_APPLIED")
        return
    shutil.copy2(SOURCE, BACKUP)
    patched = original.replace("import hashlib\nimport re", "import hashlib\nimport itertools\nimport re", 1)
    needle = '                )\n            if "original_dense" in views:\n'
    if needle not in patched:
        shutil.copy2(BACKUP, SOURCE)
        raise RuntimeError("pipeline insertion point not found")
    patched = patched.replace(needle, "                )\n" + BLOCK + '            if "original_dense" in views:\n', 1)
    SOURCE.write_text(patched, encoding="utf-8")
    print("LEXICAL_ANCHOR_VARIANT_APPLIED")


def rollback() -> None:
    if BACKUP.exists():
        shutil.copy2(BACKUP, SOURCE)
        BACKUP.unlink()
        print("LEXICAL_ANCHOR_VARIANT_ROLLED_BACK")
    else:
        print("LEXICAL_ANCHOR_VARIANT_NO_BACKUP")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "apply"
    if action == "apply":
        apply()
    elif action == "rollback":
        rollback()
    else:
        raise SystemExit("usage: apply_lexical_anchor_variant_smoke.py [apply|rollback]")
