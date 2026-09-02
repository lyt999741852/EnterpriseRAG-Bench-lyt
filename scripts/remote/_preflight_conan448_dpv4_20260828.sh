set -euo pipefail
APP=/opt/enterprise-rag-bench/app
ES='http://10.72.100.29:31920'
INDEX='enterprise-rag-qwen3-emb-v3-conan448'
echo '--- index count ---'
curl -fsS "$ES/$INDEX/_count" | python -m json.tool
echo '--- mapping dimensions ---'
curl -fsS "$ES/$INDEX/_mapping" | python -c 'import json,sys; d=json.load(sys.stdin); p=next(iter(d.values()))["mappings"]["properties"]; print({k:v for k,v in p.items() if k in ("embedding","chunk_text","document_id","source_type")})'
echo '--- local index/manifest ---'
test -d "$APP/.index_cache/full_es_qwen3_emb_v3_conan448"
test -f "$APP/.index_cache/full_es_qwen3_emb_v3_conan448/manifest.sqlite3"
ls -lh "$APP/.index_cache/full_es_qwen3_emb_v3_conan448/manifest.sqlite3"
echo '--- config and scripts ---'
test -f "$APP/configs/eval_pageindex_balanced50_conan448_rerank_question_only_llm_route_multiview_dpv4_20260828.yaml"
test -x "$APP/scripts/remote/_run_conan448_dpv4_20260828.sh"
test -x "$APP/scripts/remote/_score_conan448_dpv4_20260828.sh"
echo PREFLIGHT_OK
