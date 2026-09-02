set -u
echo '--- ES CREATION ---'
curl -fsS --max-time 20 'http://127.0.0.1:9200/enterprise-rag-e5-large-v1/_settings' \
 | /root/anaconda3/bin/python -c 'import json,sys; d=json.load(sys.stdin); s=next(iter(d.values()))["settings"].get("index",{}); print({"creation_date":s.get("creation_date"),"uuid":s.get("uuid"),"version_created":s.get("version",{}).get("created")})' || true
echo '--- BUILD LOG ---'
stat -c '%n | mtime=%y | ctime=%z | size=%s' /opt/enterprise-rag-bench/app/outputs/build_e5_20260806.log 2>/dev/null || true
head -n 25 /opt/enterprise-rag-bench/app/outputs/build_e5_20260806.log 2>/dev/null || true
tail -n 35 /opt/enterprise-rag-bench/app/outputs/build_e5_20260806.log 2>/dev/null || true
echo '--- RELATED OUTPUTS ---'
find /opt/enterprise-rag-bench/app/outputs -maxdepth 1 -type f -iname '*e5*' -printf '%f | %TY-%Tm-%Td %TH:%TM:%TS | %s\n' | sort || true
