cd /opt/enterprise-rag-bench/app
grep -n 'original_candidate_reserve\|last_retrieval_reserve' src/pipeline.py src/elasticsearch_backend.py || true
