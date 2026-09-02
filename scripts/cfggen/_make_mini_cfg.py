"""Create mini build config for end-to-end verification."""
import pathlib

src = pathlib.Path(r"d:\EnterpriseRAG-Bench\configs\full_es_qwen3_emb.yaml").read_text(encoding="utf-8")
out = src.replace("enterprise-rag-qwen3-emb-v1", "enterprise-rag-qwen3-emb-mini")
out = out.replace('alias_name: "enterprise-rag-qwen3-emb"', 'alias_name: "enterprise-rag-qwen3-emb-mini"')
out = out.replace("baseline_full_es_qwen3_emb", "mini_qwen3_emb")
out = out.replace("overwrite_index: false", "overwrite_index: false\n  max_index_chunks: 5000")
pathlib.Path(r"d:\EnterpriseRAG-Bench\configs\mini_qwen3_emb.yaml").write_text(out, encoding="utf-8")
for line in out.splitlines():
    if "index_name" in line or "max_index_chunks" in line or "name:" in line:
        print(" ", line.strip())
