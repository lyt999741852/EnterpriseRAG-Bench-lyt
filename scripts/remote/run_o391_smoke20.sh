cd /opt/enterprise-rag-bench/app
RUN=pageindex_o391_metadata_reserve_smoke20_20260901
mkdir -p outputs/$RUN
export TRANSFORMERS_OFFLINE=1
export QUESTION_PARALLELISM=1
nohup /root/anaconda3/envs/embedding_test/bin/python -u -m src.pipeline configs/eval_pageindex_o391_metadata_reserve_smoke20_20260901.yaml > outputs/$RUN/pipeline.log 2>&1 < /dev/null &
echo $! > outputs/$RUN/run.pid
echo PID=$(cat outputs/$RUN/run.pid)
