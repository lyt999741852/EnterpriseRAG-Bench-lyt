"""Generate the isolated O3.9 20-question reserve smoke config."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "configs/eval_pageindex_o1_original_reserve_smoke20_20260831.yaml"
TARGET = ROOT / "configs/eval_pageindex_o391_metadata_reserve_smoke20_20260901.yaml"

cfg = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
cfg["elasticsearch"]["index_name"] = "o391_bge_meta_bm25_20260901"
cfg["elasticsearch"]["alias_name"] = "o391_bge_meta_bm25_20260901"
cfg["retrieval"]["candidate_k"] = 500
cfg["retrieval"]["reranker"]["candidate_k"] = 120
cfg["pipeline"]["name"] = "pageindex_o391_metadata_reserve_smoke20_20260901"
cfg["pipeline"]["original_candidate_reserve"] = {
    "enabled": True,
    "max_chunks": 8,
    "insertion_stride": 4,
    "source": "raw_hybrid_tail",
}
cfg["pipeline"]["question_parallelism"] = 1
cfg["pageindex"]["manifest_path"] = ".index_cache/full_es_bge_small/manifest.sqlite3"
cfg["pageindex"]["cache_dir"] = ".pageindex_cache/o391_metadata_reserve_smoke20_20260901"
TARGET.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
print(TARGET)
