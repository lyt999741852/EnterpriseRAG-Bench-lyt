#!/usr/bin/env bash
set -euo pipefail

APP=/opt/enterprise-rag-bench/app
PYTHON=/root/anaconda3/envs/embedding_test/bin/python
cd "$APP"

test -f configs/eval_bge_semantic12_answer_schema_quota_20260813.yaml
test -f .index_cache/full_es_bge_small/manifest.sqlite3
"$PYTHON" -m py_compile src/pipeline.py
"$PYTHON" - <<'PY'
import yaml
with open("configs/eval_bge_semantic12_answer_schema_quota_20260813.yaml", encoding="utf-8") as handle:
    cfg = yaml.safe_load(handle)
assert cfg["pipeline"]["read_existing_index"] is True
assert cfg["pipeline"]["overwrite_index"] is False
assert cfg["elasticsearch"]["index_name"] == "enterprise-rag-bge-small-v1"
assert len(cfg["pipeline"]["question_ids"]) == 12
print("remote_config=OK")
PY

echo -n "cluster_health="
curl -fsS "http://127.0.0.1:9200/_cluster/health?filter_path=status,timed_out,number_of_nodes,active_primary_shards,unassigned_shards"
echo
echo -n "alias="
curl -fsS "http://127.0.0.1:9200/_alias/enterprise-rag-bge-small?filter_path=*.aliases"
echo
echo -n "index_count="
curl -fsS "http://127.0.0.1:9200/enterprise-rag-bge-small-v1/_count?filter_path=count"
echo
echo "matching_processes:"
pgrep -af "eval_bge_semantic12_answer_schema_quota_20260813.yaml" || true
