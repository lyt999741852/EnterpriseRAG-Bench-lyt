set -u
APP=/opt/enterprise-rag-bench/app
DIR="$APP/outputs/semantic30_r4_d2a_wide_candidates_20260825"
echo '--- CONFIG CONTROLS ---'
grep -nE '^  (resume|resume_legacy|question_parallelism):' "$APP/configs/eval_semantic30_r4_d2a_wide_candidates_20260825.yaml" || true
echo '--- RUN METADATA ---'
ls -l "$DIR"/run_meta* "$DIR"/answers* 2>/dev/null || true
cat "$DIR/run_meta.json" 2>/dev/null || true
echo '--- RESUME LOG ---'
sed -n '/parallel-2 resume/,$p' "$DIR/pipeline.log" | head -n 35
echo '--- OUTPUT BACKUPS ---'
find "$DIR" -maxdepth 1 -type f -printf '%f %s %TY-%Tm-%Td %TH:%TM:%TS\n' | sort
