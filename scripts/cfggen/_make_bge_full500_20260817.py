"""Create an isolated 500-question BGE full-evaluation config."""
from pathlib import Path
import re

src = Path("configs/eval_pageindex_stratified100_bge_rerank_question_only_llm_route_multiview_p0_20260814.yaml")
dst = Path("configs/eval_pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817.yaml")
text = src.read_text(encoding="utf-8")

text = re.sub(
    r"^  question_ids:\n.*?(?=^  overwrite_index:)",
    "",
    text,
    flags=re.MULTILINE | re.DOTALL,
)
text = text.replace(
    'cache_dir: ".pageindex_cache/stratified100_bge_rerank_question_only_llm_route_multiview_p0_20260814"',
    'cache_dir: ".pageindex_cache/full500_bge_rerank_question_only_llm_route_multiview_p0_20260817"',
)
text = text.replace(
    'name: "pageindex_stratified100_bge_rerank_question_only_llm_route_multiview_p0_20260814"',
    'name: "pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817"',
)
text = text.replace(
    '  api_key_env: ""\n  api_key: "lark"',
    '  api_key_env: "LARK_API_KEY"',
)
dst.write_text(text, encoding="utf-8")
print(f"created: {dst}")
