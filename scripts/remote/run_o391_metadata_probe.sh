cd /opt/enterprise-rag-bench/app
nohup /root/anaconda3/envs/embedding_test/bin/python -u scripts/diag/probe_raw_miss_topk_sweep_20260901.py --questions questions.jsonl --o0-funnel outputs/pageindex_full500_bge_dpv4_20260831/o0_funnel.json --output outputs/pageindex_full500_bge_dpv4_20260831/o391_metadata_probe.json --es http://127.0.0.1:9200 --index o391_bge_meta_bm25_20260901 --model BAAI/bge-small-en-v1.5 --workers 16 --metadata-fields > outputs/pageindex_full500_bge_dpv4_20260831/o391_metadata_probe.log 2>&1 &
echo $!
