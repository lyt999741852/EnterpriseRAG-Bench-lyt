cd /opt/enterprise-rag-bench/app
nohup /root/anaconda3/envs/embedding_test/bin/python -u scripts/diag/build_metadata_shadow_index_20260901.py --es http://127.0.0.1:9200 --source-index enterprise-rag-bge-small-v1 --target-index o391_bge_meta_bm25_20260901 --manifest .index_cache/full_es_bge_small/manifest.sqlite3 --batch-size 2000 --workers 8 --metadata-only > outputs/pageindex_full500_bge_dpv4_20260831/o391_metadata_update.log 2>&1 &
echo $!
