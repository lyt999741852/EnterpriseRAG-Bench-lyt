curl -s http://127.0.0.1:9200/o391_bge_meta_bm25_20260901/_count
curl -s -X POST http://127.0.0.1:9200/o391_bge_meta_bm25_20260901/_refresh
curl -s 'http://127.0.0.1:9200/o391_bge_meta_bm25_20260901/_search?size=0' -H 'Content-Type: application/json' -d '{"aggs":{"title_present":{"filter":{"exists":{"field":"title"}}},"path_present":{"filter":{"exists":{"field":"file_path"}}},"lexical_present":{"filter":{"exists":{"field":"lexical_context"}}}},"query":{"match_all":{}}}'
