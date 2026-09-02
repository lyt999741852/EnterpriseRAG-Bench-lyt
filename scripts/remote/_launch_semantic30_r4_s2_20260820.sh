#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
NAME=semantic30_r4_s2_parent_window_20260820
RUN="$APP/outputs/$NAME"
CONFIG="$APP/configs/eval_$NAME.yaml"
BASE_CONFIG="$APP/configs/eval_semantic30_r4_s1_lexical_anchor_20260820.yaml"

/root/anaconda3/envs/embedding_test/bin/python - "$APP/src/elasticsearch_backend.py" "$APP/src/pipeline.py" "$BASE_CONFIG" "$CONFIG" <<'PY'
import sys
from copy import deepcopy
from pathlib import Path
import yaml

backend_path, pipeline_path, base_path, config_path = map(Path, sys.argv[1:])

backend = backend_path.read_text(encoding="utf-8")
if "def neighbor_search(" not in backend:
    anchor = '''        response = self._request("POST", f"/{self.config.alias_name}/_search", payload)\n        return response.get("hits", {}).get("hits", [])\n\n    def _existing_ids'''
    replacement = '''        response = self._request("POST", f"/{self.config.alias_name}/_search", payload)\n        return response.get("hits", {}).get("hits", [])\n\n    def neighbor_search(\n        self, doc_id: str, center_index: int, radius: int\n    ) -> list[dict]:\n        radius = max(0, int(radius))\n        center_index = max(0, int(center_index))\n        response = self._request("POST", f"/{self.config.alias_name}/_search", {\n            "size": max(1, radius * 2 + 1),\n            "_source": [\n                "chunk_id", "doc_id", "source_type", "text", "chunk_index"\n            ],\n            "query": {"bool": {"filter": [\n                {"term": {"doc_id": doc_id}},\n                {"range": {"chunk_index": {\n                    "gte": max(0, center_index - radius),\n                    "lte": center_index + radius,\n                }}},\n            ]}},\n            "sort": [{"chunk_index": {"order": "asc"}}],\n        })\n        return response.get("hits", {}).get("hits", [])\n\n    def _existing_ids'''
    if anchor not in backend:
        raise SystemExit("backend neighbor anchor not found")
    backend = backend.replace(anchor, replacement, 1)
    backend_method_anchor = '''    @staticmethod\n    def get_parent_doc_ids(results: list[RetrieveResult]) -> list[str]:\n'''
    backend_method = '''    def expand_neighbors(\n        self,\n        results: list[RetrieveResult],\n        neighbor_chunks: int = 1,\n        max_seed_results: int = 3,\n        max_expanded_chunks: int = 8,\n    ) -> list[RetrieveResult]:\n        if not results:\n            return []\n        expanded = list(results)\n        seen = {item.chunk_id for item in expanded}\n        added = 0\n        for seed in results[:max(1, int(max_seed_results))]:\n            center = self.backend._chunk_index(seed.chunk_id)\n            hits = self.backend.neighbor_search(\n                seed.doc_id, center, max(0, int(neighbor_chunks))\n            )\n            for hit in hits:\n                chunk_id = hit.get("_source", {}).get("chunk_id", hit.get("_id", ""))\n                if not chunk_id or chunk_id in seen:\n                    continue\n                seen.add(chunk_id)\n                expanded.append(self._hit_to_result(\n                    hit, max(float(seed.score) * 0.7, 0.01)\n                ))\n                added += 1\n                if added >= max(0, int(max_expanded_chunks)):\n                    break\n            if added >= max(0, int(max_expanded_chunks)):\n                break\n        self.last_retrieval_trace["neighbor_expansion"] = {\n            "seed_results": min(len(results), max(1, int(max_seed_results))),\n            "neighbor_chunks": max(0, int(neighbor_chunks)),\n            "added_chunks": added,\n        }\n        return expanded\n\n    @staticmethod\n    def get_parent_doc_ids(results: list[RetrieveResult]) -> list[str]:\n'''
    if backend_method_anchor not in backend:
        raise SystemExit("backend method anchor not found")
    backend = backend.replace(backend_method_anchor, backend_method, 1)
    backend_path.write_text(backend, encoding="utf-8")
    print("ES_NEIGHBOR_EXPANSION_PATCHED")
else:
    print("ES_NEIGHBOR_EXPANSION_ALREADY_PATCHED")

pipeline = pipeline_path.read_text(encoding="utf-8")
old = '''        expansion_cfg = retrieval_cfg.get("parent_expansion", {})\n        if expansion_cfg.get("enabled", False):\n            if uses_elasticsearch:\n                raise ValueError(\n                    "ES neighbor expansion is not enabled yet; "\n                    "set retrieval.parent_expansion.enabled=false"\n                )\n            results = worker_retriever.expand_neighbors(\n                results,\n                neighbor_chunks=expansion_cfg.get("neighbor_chunks", 1),\n            )\n'''
new = '''        expansion_cfg = retrieval_cfg.get("parent_expansion", {})\n        expansion_types = expansion_cfg.get("types", [])\n        if expansion_cfg.get("enabled", False) and (\n            not expansion_types or retrieval_type_key in expansion_types\n        ):\n            results = worker_retriever.expand_neighbors(\n                results,\n                neighbor_chunks=expansion_cfg.get("neighbor_chunks", 1),\n                max_seed_results=expansion_cfg.get("max_seed_results", 3),\n                max_expanded_chunks=expansion_cfg.get("max_expanded_chunks", 8),\n            )\n'''
if old in pipeline:
    pipeline = pipeline.replace(old, new, 1)
    pipeline_path.write_text(pipeline, encoding="utf-8")
    print("PIPELINE_PARENT_EXPANSION_PATCHED")
elif "expansion_types = expansion_cfg.get(\"types\", [])" in pipeline:
    print("PIPELINE_PARENT_EXPANSION_ALREADY_PATCHED")
else:
    raise SystemExit("pipeline parent expansion anchor not found")

cfg = deepcopy(yaml.safe_load(base_path.read_text(encoding="utf-8")))
cfg["pipeline"]["name"] = "semantic30_r4_s2_parent_window_20260820"
cfg["pipeline"]["resume"] = False
cfg["pipeline"]["resume_legacy"] = False
cfg["retrieval"]["parent_expansion"] = {
    "enabled": True,
    "types": ["semantic"],
    "neighbor_chunks": 1,
    "max_seed_results": 3,
    "max_expanded_chunks": 8,
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
