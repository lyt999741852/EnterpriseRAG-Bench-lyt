"""Apply/rollback the isolated O1 original-candidate reserve patch."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


SOURCE = Path("src/pipeline.py")
BACKUP = Path("src/pipeline.py.o1_original_candidate_reserve.bak")
MARKER = '"original_candidate_reserve"'

PATCH = '''
        # O1 is opt-in and keeps a bounded reserve from the original
        # post-rerank BM25+dense candidates after PageIndex routing. It is
        # independent of benchmark question type and does not lock a target.
        pre_pageindex_results = list(results)
'''

RESERVE = '''
            reserve_cfg = pipeline.get("original_candidate_reserve", {})
            if reserve_cfg.get("enabled", False):
                reserve_n = max(0, int(reserve_cfg.get("max_chunks", 4)))
                stride = max(1, int(reserve_cfg.get("insertion_stride", 4)))
                routed_ids = {item.chunk_id for item in results}
                reserve_items = [
                    item for item in pre_pageindex_results
                    if item.chunk_id not in routed_ids
                ][:reserve_n]
                if reserve_items:
                    merged: list = []
                    reserve_index = 0
                    for index, item in enumerate(results):
                        if (
                            index > 0
                            and index % stride == 0
                            and reserve_index < len(reserve_items)
                        ):
                            merged.append(reserve_items[reserve_index])
                            reserve_index += 1
                        merged.append(item)
                    while reserve_index < len(reserve_items):
                        merged.append(reserve_items[reserve_index])
                        reserve_index += 1
                    results = merged
                worker_router.last_trace["original_candidate_reserve"] = {
                    "enabled": True,
                    "requested_chunks": reserve_n,
                    "added_chunks": len(reserve_items),
                    "insertion_stride": stride,
                    "source": reserve_cfg.get(
                        "source", "post_rerank_before_pageindex"
                    ),
                    "chunk_ids": [item.chunk_id for item in reserve_items],
                }

'''


def apply() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    if MARKER in text:
        print("O1_ALREADY_APPLIED")
        return
    shutil.copy2(SOURCE, BACKUP)
    anchor = '        use_pageindex = (\n'
    if anchor not in text:
        raise RuntimeError("use_pageindex anchor not found")
    text = text.replace(anchor, PATCH + "\n" + anchor, 1)
    anchor = (
        '            results = worker_router.route(\n'
        '                query,\n'
        '                question_type,\n'
        '                results,\n'
        '                retrieve_callback=retrieve_query,\n'
        '            )\n'
    )
    if anchor not in text:
        shutil.copy2(BACKUP, SOURCE)
        raise RuntimeError("pageindex route anchor not found")
    text = text.replace(anchor, anchor + RESERVE, 1)
    SOURCE.write_text(text, encoding="utf-8")
    print("O1_APPLIED")


def rollback() -> None:
    if BACKUP.exists():
        shutil.copy2(BACKUP, SOURCE)
        BACKUP.unlink()
        print("O1_ROLLED_BACK")
    else:
        print("O1_NO_BACKUP")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "apply"
    if action == "apply":
        apply()
    elif action == "rollback":
        rollback()
    else:
        raise SystemExit("usage: apply_o1_original_candidate_reserve.py [apply|rollback]")
