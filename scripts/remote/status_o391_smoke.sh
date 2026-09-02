cd /opt/enterprise-rag-bench/app
RUN=pageindex_o391_metadata_reserve_smoke20_20260901
tail -n 40 outputs/$RUN/pipeline.log
ps -p $(cat outputs/$RUN/run.pid) -o pid=,stat=,etime=,cmd= || true
ls -l outputs/$RUN/answers.jsonl outputs/$RUN/route_trace.jsonl 2>/dev/null || true
