set -u
echo '--- tool versions ---'
command -v python || true
python --version 2>&1 || true
command -v huggingface-cli || true
huggingface-cli --version 2>&1 || true
command -v hf || true
hf --version 2>&1 || true
command -v git || true
git lfs version 2>&1 || true
echo '--- corpus/index size ---'
du -sh /opt/enterprise-rag-bench/app/corpus /opt/enterprise-rag-bench/app/.index_cache/full_es_bge_small 2>/dev/null || true
find /opt/enterprise-rag-bench/app/corpus -type f 2>/dev/null | wc -l || true
echo '--- bge-large candidates ---'
find /data06 /opt/enterprise-rag-bench /root/.cache -maxdepth 4 -type d -iname '*bge*large*' 2>/dev/null | head -50
echo '--- ES status/counts ---'
curl -sS http://127.0.0.1:9200/_cluster/health 2>/dev/null | head -c 1000 || true
echo
curl -sS http://127.0.0.1:9200/enterprise-rag-bge-small-v1/_count 2>/dev/null || true
echo
