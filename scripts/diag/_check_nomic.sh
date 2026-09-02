#!/bin/bash
echo "=== ollama ==="
which ollama 2>/dev/null && ollama list 2>/dev/null | head -20 || echo "no ollama cli"
echo "=== find nomic (common paths) ==="
find /opt /root /data06 -maxdepth 6 -iname "*nomic*" 2>/dev/null | head -20
echo "=== HF cache models ==="
ls /root/.cache/huggingface/hub/ 2>/dev/null
ls /opt/enterprise-rag-bench/model_cache/hub/ 2>/dev/null
echo "=== embedding-related dirs ==="
ls -d /data06/*embed* /data06/*nomic* /opt/*nomic* 2>/dev/null
echo "=== mini build status ==="
ps aux | grep build_es_index | grep -v grep | head -2
tail -c 400 /opt/enterprise-rag-bench/app/outputs/build_mini_qwen3_emb.log 2>/dev/null
curl -s -m 10 'http://127.0.0.1:9200/enterprise-rag-qwen3-emb-mini/_count' 2>/dev/null | head -c 120
echo
