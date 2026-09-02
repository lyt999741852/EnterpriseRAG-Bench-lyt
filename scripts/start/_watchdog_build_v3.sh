#!/bin/bash
# Watchdog for v3 Conan448 ES build: auto-restart on crash, loop forever.
# Start detached (survives SSH session teardown):
#   setsid nohup bash scripts/start/_watchdog_build_v3.sh \
#     > outputs/watchdog_v3.log 2>&1 &
# The watchdog itself never matches pgrep -f 'src.build_es_index' because its
# own command line is 'bash scripts/start/_watchdog_build_v3.sh'.
cd /opt/enterprise-rag-bench/app || exit 1
source /root/anaconda3/etc/profile.d/conda.sh
while true; do
    if ! pgrep -f 'src.build_es_index' > /dev/null; then
        echo "[$(date '+%F %T')] build process dead, restarting..." >> outputs/watchdog_v3.log
        conda activate embedding_test
        export EMBEDDING_API_KEY=123456
        nohup python -u -m src.build_es_index configs/full_es_qwen3_emb_v3_conan448.yaml \
          >> outputs/build_v3_conan448_20260812.log 2>&1 &
        echo "[$(date '+%F %T')] restarted pid $!" >> outputs/watchdog_v3.log
    fi
    sleep 300
done
