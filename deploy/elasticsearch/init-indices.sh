#!/usr/bin/env sh
set -eu

ES_URL="${ES_URL:-http://127.0.0.1:9200}"
INDEX_NAME="enterprise-rag-bge-small-v1"
ALIAS_NAME="enterprise-rag-bge-small"

if curl --fail --silent --head "${ES_URL}/${INDEX_NAME}" >/dev/null; then
  echo "Index ${INDEX_NAME} already exists; no changes made."
  exit 0
fi

curl --fail --silent --show-error \
  -X PUT "${ES_URL}/${INDEX_NAME}" \
  -H 'Content-Type: application/json' \
  --data-binary @- <<'JSON'
{
  "aliases": {
    "enterprise-rag-bge-small": {}
  },
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "refresh_interval": "30s"
  },
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "chunk_id": { "type": "keyword" },
      "doc_id": { "type": "keyword" },
      "source_type": { "type": "keyword" },
      "file_path": { "type": "keyword", "ignore_above": 2048 },
      "title": {
        "type": "text",
        "fields": { "keyword": { "type": "keyword", "ignore_above": 512 } }
      },
      "text": { "type": "text" },
      "chunk_index": { "type": "integer" },
      "char_start": { "type": "integer" },
      "char_end": { "type": "integer" },
      "content_hash": { "type": "keyword" },
      "embedding_model": { "type": "keyword" },
      "embedding": {
        "type": "dense_vector",
        "dims": 384,
        "index": true,
        "similarity": "cosine"
      },
      "created_at": { "type": "date" }
    }
  }
}
JSON

echo
echo "Created ${INDEX_NAME} with alias ${ALIAS_NAME}."
