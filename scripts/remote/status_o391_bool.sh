cd /opt/enterprise-rag-bench/app
tail -n 50 outputs/pageindex_full500_bge_dpv4_20260831/o391_metadata_bool_probe.log
ls -l outputs/pageindex_full500_bge_dpv4_20260831/o391_metadata_bool_probe.json || true
pgrep -af 'probe_raw_miss_topk_sweep.*bool' || true
