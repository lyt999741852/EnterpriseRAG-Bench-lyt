set -u
grep -RniE 'model|embedding|dimension|port|volume|path' /data01/cihai/cihai-embedding-v3/deployment.yaml /data01/cihai/cihai-embedding-v3/*.py /data01/cihai/cihai-embedding-v3/*.log 2>/dev/null | head -160 || true
