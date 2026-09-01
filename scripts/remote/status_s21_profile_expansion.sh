cd /opt/enterprise-rag-bench/app
echo '--- process ---'
pgrep -af probe_s21_profile_expansion_20260901.py || true
echo '--- output ---'
ls -lh outputs/pageindex_full500_bge_dpv4_20260831/s2_1_profile_expansion_20260901.* 2>/dev/null || true
echo '--- log tail ---'
tail -n 30 outputs/pageindex_full500_bge_dpv4_20260831/s2_1_profile_expansion_20260901.log 2>/dev/null || true
