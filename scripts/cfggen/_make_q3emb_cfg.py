"""Create 50-question eval config for the new vector library."""
import pathlib

SRC = r"d:\EnterpriseRAG-Bench\configs\eval_pageindex_balanced50_p1.yaml"
DST = r"d:\EnterpriseRAG-Bench\configs\eval_pageindex_balanced50_q3emb.yaml"

text = pathlib.Path(SRC).read_text(encoding="utf-8")

# 1) pipeline name (new output dir)
text = text.replace(
    'name: "pageindex_balanced50_p1_20260804"',
    'name: "pageindex_balanced50_q3emb_20260805"',
)
# 2) index dir -> new library cache
text = text.replace(
    'index_dir: ".index_cache/full_es_bge_small"',
    'index_dir: ".index_cache/full_es_qwen3_emb"',
)
# 3) chunking -> hierarchical-v1
text = text.replace(
    '  version: "fixed-v2"\n  manifest_enabled: true\n  chunk_size: 512\n  chunk_overlap: 0',
    '  version: "hierarchical-v1"\n  manifest_enabled: true\n  chunk_size: 384\n  chunk_overlap: 64',
)
# 4) embedding -> internal API
text = text.replace(
    '''embedding:
  provider: "sentence_transformers"
  model_name: "BAAI/bge-small-en-v1.5"
  device: "cuda"
  batch_size: 256
  dimension: 384
  revision: "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"''',
    '''embedding:
  provider: "openai_compatible"
  model_name: "embedding"
  api_base: "http://10.72.55.209:7993/v1"
  api_key_env: "EMBEDDING_API_KEY"
  device: "cpu"
  batch_size: 512
  dimension: 1792''',
)
# 5) ES index names
text = text.replace(
    '  index_name: "enterprise-rag-bge-small-v1"\n  alias_name: "enterprise-rag-bge-small"',
    '  index_name: "enterprise-rag-qwen3-emb-v1"\n  alias_name: "enterprise-rag-qwen3-emb"',
)
# 6) pageindex cache dir (independent for the new library run)
text = text.replace(
    '  cache_dir: ".pageindex_cache/balanced50_v52"',
    '  cache_dir: ".pageindex_cache/balanced50_q3emb"',
)
# 7) manifest path for pageindex -> new library manifest
text = text.replace(
    '  manifest_path: ".index_cache/full_es_bge_small/manifest.sqlite3"',
    '  manifest_path: ".index_cache/full_es_qwen3_emb/manifest.sqlite3"',
)

pathlib.Path(DST).write_text(text, encoding="utf-8")
print("created:", DST)
# verify key fields
for line in text.splitlines():
    if any(k in line for k in ("name: \"pageindex_balanced50", "index_dir:", "chunk_size:", "chunk_overlap:", "version: \"hierarchical", "model_name:", "api_base:", "index_name:", "cache_dir:", "manifest_path:")):
        print(" ", line.strip())
