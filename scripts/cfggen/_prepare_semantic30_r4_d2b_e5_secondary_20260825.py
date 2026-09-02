"""Create D2b: Semantic-only E5-large secondary dense recall over S1."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "configs" / "eval_semantic30_r4_s1_lexical_anchor_20260820.yaml"
OUT = ROOT / "configs" / "eval_semantic30_r4_d2b_e5_secondary_20260825.yaml"

cfg = deepcopy(yaml.safe_load(BASE.read_text(encoding="utf-8")))
cfg["pipeline"].update({
    "name": "semantic30_r4_d2b_e5_secondary_20260825",
    "resume": False,
    "resume_legacy": False,
    "question_parallelism": 1,
})

retrieval = cfg["retrieval"]
# D2b branches from S1: do not carry forward D2a's ineffective 180-candidate
# expansion, so the only retrieval-quality delta is the E5 secondary view.
retrieval["reranker"]["candidate_k"] = 120
retrieval["semantic_secondary_dense"] = {
    "enabled": True,
    "types": ["semantic"],
    "top_k": 80,
    "max_chunks_per_document": 2,
    "collapse_recursive_partitions": True,
    "embedding": {
        "provider": "sentence_transformers",
        "model_name": "/data06/embedding-models/multilingual-e5-large",
        # CPU avoids taking capacity from the shared A800 services. This branch
        # runs only for Semantic-routed questions and is candidate-only.
        "device": "cpu",
        "batch_size": 16,
        "dimension": 1024,
        "fp16": False,
        "query_prefix": "query: ",
        "document_prefix": "passage: ",
    },
    "elasticsearch": {
        "url": "http://127.0.0.1:9200",
        "index_name": "enterprise-rag-e5-large-v1",
        "alias_name": "enterprise-rag-e5-large",
        "bulk_size": 256,
        "request_timeout": 180,
        "dense_mode": "script_score",
    },
}

multi_view = retrieval["multi_view"]
multi_view["weights"]["semantic_secondary_dense"] = 0.45
semantic_views = multi_view["routes"]["semantic"]
if "semantic_secondary_dense" not in semantic_views:
    semantic_views.append("semantic_secondary_dense")
multi_view["route_weights"]["semantic"]["semantic_secondary_dense"] = 0.45

OUT.write_text(
    "# D2b: S1 + E5-large (1024-dim) Semantic-only secondary dense candidates.\n"
    "# PageIndex OFF; --no-correction is applied by the remote score watcher.\n"
    + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
    encoding="utf-8",
)
print(OUT)
