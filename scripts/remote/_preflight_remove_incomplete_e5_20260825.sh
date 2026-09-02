set -u
APP=/opt/enterprise-rag-bench/app
RUN="$APP/outputs/semantic30_r4_d2b_e5_secondary_20260825"
CACHE="$APP/.index_cache/full_es_e5"
echo '--- D2B PROCESS ---'
if [ -f "$RUN/run.pid" ]; then
  pid=$(cat "$RUN/run.pid")
  echo "pid=$pid"
  ps -p "$pid" -o pid,stat,etime,cmd || true
fi
pgrep -af 'src.pipeline.*semantic30_r4_d2b_e5_secondary_20260825|metrics_based_eval.*semantic30_r4_d2b_e5_secondary_20260825' || true
echo '--- E5 INDEX ---'
curl -fsS --max-time 15 'http://127.0.0.1:9200/enterprise-rag-e5-large-v1/_count' || true
echo
echo '--- DELETE TARGETS ---'
for path in "$RUN" "$CACHE"; do
  if [ -e "$path" ]; then
    realpath "$path"
    du -sh "$path"
  else
    echo "MISSING $path"
  fi
done
