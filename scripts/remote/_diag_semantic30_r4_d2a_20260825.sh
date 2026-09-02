set -u
APP=/opt/enterprise-rag-bench/app
RUN=semantic30_r4_d2a_wide_candidates_20260825
DIR="$APP/outputs/$RUN"
pid=$(cat "$DIR/run.pid" 2>/dev/null || true)
echo '--- TIME / PROGRESS ---'
date -Is
wc -l "$DIR/answers.jsonl" 2>/dev/null || true
stat -c 'answers_mtime=%y size=%s' "$DIR/answers.jsonl" 2>/dev/null || true
echo '--- PIPELINE RESOURCE ---'
ps -p "$pid" -o pid,stat,etime,pcpu,pmem,rss,vsz,cmd 2>/dev/null || true
ps -eo pid,ppid,stat,etime,pcpu,pmem,rss,cmd --sort=-pcpu | head -n 20
echo '--- HOST ---'
uptime
free -h
nproc
echo '--- RECENT TIMED EVENTS ---'
grep -E '\[[0-9]+/30\]|query_rewrite|answer_intent|semantic_rescue|Generating answers' "$DIR/pipeline.log" | tail -n 45
