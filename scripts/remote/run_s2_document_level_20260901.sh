cd /opt/enterprise-rag-bench/app
mkdir -p outputs/pageindex_full500_bge_dpv4_20260831
nohup /root/anaconda3/envs/embedding_test/bin/python -u scripts/diag/probe_s2_document_level_20260901.py --questions questions.jsonl --o0-funnel outputs/pageindex_full500_bge_dpv4_20260831/o0_funnel.json --output outputs/pageindex_full500_bge_dpv4_20260831/s2_document_level_20260901.json --es http://127.0.0.1:9200 --index enterprise-rag-bge-small-v1 --model BAAI/bge-small-en-v1.5 --workers 16 > outputs/pageindex_full500_bge_dpv4_20260831/s2_document_level_20260901.log 2>&1 &
echo $!
