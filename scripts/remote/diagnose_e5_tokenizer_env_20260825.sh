#!/usr/bin/env bash
set +e
source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
echo '--- python ---'
which python
python -V
echo '--- packages ---'
python /tmp/e5_tokenizer_probe.py --packages
echo '--- model files ---'
ls -lh /data06/embedding-models/multilingual-e5-large/config.json /data06/embedding-models/multilingual-e5-large/tokenizer.json /data06/embedding-models/multilingual-e5-large/tokenizer_config.json /data06/embedding-models/multilingual-e5-large/sentencepiece.bpe.model 2>&1
echo '--- model config ---'
python /tmp/e5_tokenizer_probe.py --config
echo '--- tokenizer load (20s timeout) ---'
timeout 20s python -u /tmp/e5_tokenizer_probe.py --load
echo "tokenizer_exit=$?"
