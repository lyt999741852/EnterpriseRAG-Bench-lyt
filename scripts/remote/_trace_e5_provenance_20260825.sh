set -u
echo '--- ES INDEX METADATA ---'
curl -fsS --max-time 20 'http://127.0.0.1:9200/enterprise-rag-e5-large-v1/_settings?flat_settings=true' \
 | /root/anaconda3/bin/python -c 'import json,sys; d=json.load(sys.stdin); s=next(iter(d.values()))["settings"]["index"]; print({k:s.get(k) for k in ("creation_date","creation_date_string","uuid","version.created")})' || true
echo '--- E5 CACHE TIMESTAMPS ---'
for path in \
  /opt/enterprise-rag-bench/app/.index_cache/full_es_e5 \
  /opt/enterprise-rag-bench/app/.index_cache/full_es_e5/es_build_progress.json \
  /opt/enterprise-rag-bench/app/outputs/build_es_e5.log \
  /opt/enterprise-rag-bench/app/outputs/build_e5.log \
  /data06/embedding-models/multilingual-e5-large; do
  if [ -e "$path" ]; then
    stat -c '%n | birth=%w | mtime=%y | ctime=%z' "$path"
  else
    echo "MISSING $path"
  fi
done
echo '--- EARLIEST MODEL FILES ---'
find /data06/embedding-models/multilingual-e5-large -xdev -type f -printf '%TY-%Tm-%Td %TH:%TM:%TS %p\n' 2>/dev/null | sort | head -n 12
echo '--- PROJECT HISTORY HITS ---'
grep -RIn --exclude-dir=.git -E 'full_es_e5|multilingual-e5-large|enterprise-rag-e5-large' \
  /opt/enterprise-rag-bench/app/outputs \
  /opt/enterprise-rag-bench/app/docs \
  /opt/enterprise-rag-bench/app/*.md 2>/dev/null | head -n 80 || true
