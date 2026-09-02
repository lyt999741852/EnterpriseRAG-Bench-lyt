#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
NAME=semantic30_r4_s3_anchor_rescue_20260821
RUN="$APP/outputs/$NAME"
CONFIG="$APP/configs/eval_$NAME.yaml"
BASE_CONFIG="$APP/configs/eval_semantic30_r4_s1_lexical_anchor_20260820.yaml"

/root/anaconda3/envs/embedding_test/bin/python - "$APP/src/pipeline.py" "$BASE_CONFIG" "$CONFIG" <<'PY'
import sys
from copy import deepcopy
from pathlib import Path
import yaml

pipeline_path, base_path, config_path = map(Path, sys.argv[1:])
pipeline = pipeline_path.read_text(encoding="utf-8")
if "semantic_anchor_rescue" not in pipeline:
    pipeline = pipeline.replace(
        "import hashlib\nimport sys\n",
        "import hashlib\nimport re\nimport sys\n",
        1,
    )
    pipeline = pipeline.replace(
        "        semantic_rescue_trace: dict = {}\n        retrieval_stage_trace: dict = {\"views\": []}\n",
        "        semantic_rescue_trace: dict = {}\n"
        "        semantic_anchor_trace: dict = {}\n"
        "        semantic_keyword_results: list = []\n"
        "        retrieval_stage_trace: dict = {\"views\": []}\n",
        1,
    )
    old_keyword = '''            if "original_keyword" in views:\n                add_view(\n                    "original_keyword",\n                    retrieve_view(query, "keyword"),\n                    view_weight("original_keyword", 1.2),\n                )\n'''
    new_keyword = '''            if "original_keyword" in views:\n                keyword_results = retrieve_view(query, "keyword")\n                if retrieval_type_key == "semantic":\n                    semantic_keyword_results = keyword_results\n                add_view(\n                    "original_keyword",\n                    keyword_results,\n                    view_weight("original_keyword", 1.2),\n                )\n'''
    if old_keyword not in pipeline:
        raise SystemExit("S3 keyword-view anchor not found")
    pipeline = pipeline.replace(old_keyword, new_keyword, 1)
    anchor = '''        if semantic_rescue_cfg.get("enabled", False) and reranker_enabled:\n'''
    helper = r'''        semantic_anchor_cfg = retrieval_cfg.get("semantic_anchor_rescue", {})
        if (
            semantic_anchor_cfg.get("enabled", False)
            and retrieval_type_key in semantic_anchor_cfg.get("types", ["semantic"])
            and semantic_keyword_results
        ):
            # Preserve a small, document-level BM25 reserve for Semantic
            # questions. This uses only query/document lexical overlap.
            try:
                stop_tokens = {
                    "about", "after", "also", "been", "being", "between",
                    "could", "does", "from", "have", "into", "more", "most",
                    "other", "over", "should", "some", "than", "that", "their",
                    "there", "these", "they", "this", "those", "through", "under",
                    "what", "when", "where", "which", "while", "with", "would",
                    "your", "explain", "describe", "please", "system", "company",
                    "document", "documents", "question", "following", "according",
                }

                def lexical_tokens(value: str) -> set[str]:
                    return {
                        token.lower()
                        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", value or "")
                        if token.lower() not in stop_tokens
                    }

                query_tokens = lexical_tokens(query)
                keyword_top_n = max(1, int(semantic_anchor_cfg.get("keyword_top_n", 6)))
                max_anchor_docs = max(0, int(semantic_anchor_cfg.get("max_anchor_docs", 2)))
                max_chunks_per_doc = max(1, int(semantic_anchor_cfg.get("max_chunks_per_doc", 2)))
                min_query_token_hits = max(1, int(semantic_anchor_cfg.get("min_query_token_hits", 2)))
                selected_docs: list[str] = []
                selected_items: list = []
                doc_hits: dict[str, int] = {}
                existing_chunk_ids = {existing.chunk_id for existing in results}
                for item in semantic_keyword_results[:keyword_top_n]:
                    if not item.doc_id:
                        continue
                    hits = len(query_tokens & lexical_tokens(item.text))
                    doc_hits[item.doc_id] = max(doc_hits.get(item.doc_id, 0), hits)
                    if hits < min_query_token_hits or item.doc_id in selected_docs:
                        continue
                    selected_docs.append(item.doc_id)
                    if len(selected_docs) >= max_anchor_docs:
                        break
                for doc_id in selected_docs:
                    added_for_doc = 0
                    seen_for_doc: set[str] = set()
                    for item in semantic_keyword_results:
                        if item.doc_id != doc_id or item.chunk_id in existing_chunk_ids:
                            continue
                        if item.chunk_id in seen_for_doc:
                            continue
                        selected_items.append(item)
                        seen_for_doc.add(item.chunk_id)
                        added_for_doc += 1
                        if added_for_doc >= max_chunks_per_doc:
                            break
                if selected_items:
                    insertion_after = max(0, int(semantic_anchor_cfg.get("insertion_after_chunks", 8)))
                    base_budget = max(0, rerank_top_n - len(selected_items))
                    prefix = results[:min(insertion_after, base_budget)]
                    suffix = results[len(prefix):base_budget]
                    results = prefix + selected_items + suffix
                semantic_anchor_trace = {
                    "query_tokens": sorted(query_tokens),
                    "keyword_top_n": keyword_top_n,
                    "document_hits": doc_hits,
                    "selected_document_ids": selected_docs,
                    "selected_chunk_ids": [item.chunk_id for item in selected_items],
                }
                if selected_items:
                    print(f"  [semantic_anchor] {qid}: {len(selected_items)} lexical anchor chunk(s) reserved")
            except Exception as exc:
                semantic_anchor_trace = {"error": str(exc)}
                print(f"  [semantic_anchor] skipped {qid}: {exc}")

'''
    if anchor not in pipeline:
        raise SystemExit("S3 insertion anchor not found")
    pipeline = pipeline.replace(anchor, helper + anchor, 1)
    trace_anchor = '''        if semantic_rescue_trace:\n            route_trace["semantic_rescue"] = semantic_rescue_trace\n'''
    trace_replacement = trace_anchor + '''        if semantic_anchor_trace:\n            route_trace["semantic_anchor_rescue"] = semantic_anchor_trace\n'''
    if trace_anchor not in pipeline:
        raise SystemExit("S3 trace anchor not found")
    pipeline = pipeline.replace(trace_anchor, trace_replacement, 1)
    pipeline_path.write_text(pipeline, encoding="utf-8")
    print("PIPELINE_S3_ANCHOR_RESCUE_PATCHED")
else:
    print("PIPELINE_S3_ANCHOR_RESCUE_ALREADY_PATCHED")

cfg = deepcopy(yaml.safe_load(base_path.read_text(encoding="utf-8")))
cfg["pipeline"]["name"] = "semantic30_r4_s3_anchor_rescue_20260821"
cfg["pipeline"]["resume"] = False
cfg["pipeline"]["resume_legacy"] = False
cfg["retrieval"]["semantic_anchor_rescue"] = {
    "enabled": True,
    "types": ["semantic"],
    "keyword_top_n": 6,
    "max_anchor_docs": 2,
    "max_chunks_per_doc": 2,
    "min_query_token_hits": 2,
    "insertion_after_chunks": 8,
}
config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
print(config_path)
PY

mkdir -p "$RUN"
if [ -f "$RUN/run.pid" ] && kill -0 "$(cat "$RUN/run.pid")" 2>/dev/null; then
  echo "ALREADY_RUNNING PID=$(cat "$RUN/run.pid")"
  exit 0
fi

export LARK_API_KEY=lark
export EMBEDDING_API_KEY=123456
export TRANSFORMERS_OFFLINE=1
export QUESTION_PARALLELISM=1
cd "$APP"
nohup /root/anaconda3/envs/embedding_test/bin/python -u -m src.pipeline "$CONFIG" > "$RUN/pipeline.log" 2>&1 < /dev/null &
echo $! > "$RUN/run.pid"

nohup bash -c '
  set -u
  while true; do
    if [ -s "$0/answers.jsonl" ] && [ "$(wc -l < "$0/answers.jsonl")" -ge 30 ]; then
      export LLM_PROVIDER=openai
      export LLM_API_KEY="$LARK_API_KEY"
      export LLM_MODEL_NAME=lark
      export CHEAP_LLM_MODEL_NAME=lark
      export LLM_API_BASE=http://10.72.100.35:7777/v1
      cd "$1/EnterpriseRAG-Bench"
      /root/anaconda3/bin/python -m src.scripts.answer_evaluation.metrics_based_eval \
        --questions-file "$1/questions.jsonl" \
        --answers-file "$0/answers.jsonl" \
        --results-file "$0/results.json" \
        --parallelism 2 --no-correction --resume > "$0/score.log" 2>&1
      break
    fi
    sleep 20
  done
' "$RUN" "$APP" > "$RUN/score_watch.log" 2>&1 < /dev/null &
echo "PIPELINE_PID=$(cat "$RUN/run.pid")"
echo "RUN=$RUN"
