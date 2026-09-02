set -u
cd /opt/enterprise-rag-bench/app
echo '=== PROCESS ==='
pgrep -af run_s3_no_pageindex_agentic_20260902.py || true
echo '=== FILES ==='
find outputs/s3_20260902 -maxdepth 2 -type f -printf '%p %s bytes\n' 2>/dev/null | sort || true
echo '--- s3.0 ---'
tail -n 8 outputs/s3_20260902/s3_0_four_lane_recall.log 2>/dev/null || true
echo '--- s3.1 ---'
tail -n 8 outputs/s3_20260902/s3_1/run.log 2>/dev/null || true
echo '--- s3.2 ---'
tail -n 8 outputs/s3_20260902/s3_2/run.log 2>/dev/null || true
