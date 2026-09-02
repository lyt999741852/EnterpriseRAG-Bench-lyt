"""Temporarily expose raw hybrid tail candidates for append-only reserve smoke."""
from pathlib import Path
import shutil
import sys

PIPE = Path("src/pipeline.py")
BACK_PIPE = Path("src/pipeline.py.o391_append_reserve.bak")
BACK_ES = Path("src/elasticsearch_backend.py.o391_append_reserve.bak")
ES = Path("src/elasticsearch_backend.py")
MARKER = "o391_append_reserve"

def apply():
    p = PIPE.read_text(encoding="utf-8")
    e = ES.read_text(encoding="utf-8")
    if MARKER in p or MARKER in e:
        print("O391_ALREADY_APPLIED"); return
    shutil.copy2(PIPE, BACK_PIPE); shutil.copy2(ES, BACK_ES)
    anchor = '        ranked = sorted(candidates.values(), key=lambda item: -item[1])[:self.top_k]\n'
    repl = '''        ranked_all = sorted(candidates.values(), key=lambda item: -item[1])
        ranked = ranked_all[:self.top_k]
        # o391_append_reserve: retain a bounded raw tail without enlarging reranker input.
        self.last_retrieval_reserve = [
            self._hit_to_result(hit, score)
            for hit, score in ranked_all[self.top_k:self.candidate_k]
        ]
'''
    if anchor not in e: raise RuntimeError("ES ranked anchor missing")
    e = e.replace(anchor, repl, 1)
    anchor2 = '        pre_rerank = list(results)\n'
    repl2 = '''        pre_rerank = list(results)
        # o391_append_reserve: raw tail is appended only after rerank; reranker stays fixed.
        reserve_cfg = pipeline.get("original_candidate_reserve", {})
        reserve_items = []
        reserve_n = 0
        if reserve_cfg.get("enabled", False) and reserve_cfg.get("source") == "raw_hybrid_tail":
            raw_tail = list(getattr(worker_retriever, "last_retrieval_reserve", []))
            existing = {getattr(item, "chunk_id", "") for item in pre_rerank}
            reserve_n = max(0, int(reserve_cfg.get("max_chunks", 8)))
            reserve_items = [item for item in raw_tail if getattr(item, "chunk_id", "") not in existing][:reserve_n]
'''
    if anchor2 not in p: raise RuntimeError("pipeline pre_rerank anchor missing")
    p = p.replace(anchor2, repl2, 1)
    anchor3 = '        results = rerank_candidates(query, results, rerank_top_n)\n'
    repl3 = '''        results = rerank_candidates(query, results, rerank_top_n)
        if reserve_cfg.get("enabled", False) and reserve_cfg.get("source") == "raw_hybrid_tail" and reserve_items:
            results = list(results) + reserve_items
            retrieval_stage_trace["raw_hybrid_tail_reserve"] = {
                "requested": reserve_n,
                "added": len(reserve_items),
                "chunk_ids": [getattr(item, "chunk_id", "") for item in reserve_items],
                "rerank_input_count": len(pre_rerank),
                "final_count": len(results),
            }
'''
    if anchor3 not in p: raise RuntimeError("pipeline rerank anchor missing")
    p = p.replace(anchor3, repl3, 1)
    PIPE.write_text(p, encoding="utf-8")
    ES.write_text(e, encoding="utf-8")
    print("O391_APPLIED")

def rollback():
    if BACK_PIPE.exists(): shutil.copy2(BACK_PIPE, PIPE); BACK_PIPE.unlink()
    if BACK_ES.exists(): shutil.copy2(BACK_ES, ES); BACK_ES.unlink()
    print("O391_ROLLED_BACK")

if __name__ == "__main__":
    (apply if len(sys.argv) < 2 or sys.argv[1] == "apply" else rollback)()
