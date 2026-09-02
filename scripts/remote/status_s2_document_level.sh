cd /opt/enterprise-rag-bench/app
tail -n 30 outputs/pageindex_full500_bge_dpv4_20260831/s2_document_level_20260901.log
ls -l outputs/pageindex_full500_bge_dpv4_20260831/s2_document_level_20260901.json 2>/dev/null || true
pgrep -af 'probe_s2_document_level_20260901' || true
