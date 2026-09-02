set -u
for d in /opt/enterprise-rag-bench/model_cache/hub/models--BAAI--bge-small-en-v1.5 /root/.cache/huggingface/hub/models--sentosa--jionglin-embedding /root/.cache/torch/sentence_transformers/sentosa_jionglin-embedding /data/embedding-models/Conan-embedding-v1; do
  echo "--- $d ---"
  if [ -d "$d" ]; then du -sh "$d" 2>/dev/null; find "$d" -maxdepth 3 -type f \( -name config.json -o -name modules.json -o -name sentence_bert_config.json -o -name tokenizer_config.json -o -name README* \) -print 2>/dev/null | head -20; else echo missing; fi
done
echo '--- local BGE snapshots ---'
find /opt/enterprise-rag-bench/model_cache/hub/models--BAAI--bge-small-en-v1.5/snapshots -mindepth 1 -maxdepth 1 -type d -print 2>/dev/null
echo '--- cached model names in configs ---'
grep -RInE 'embedding.*model|model_name:.*(bge|e5|gte|jina|nomic|sentosa)' /opt/enterprise-rag-bench/app/configs /opt/enterprise-rag-bench/app/conan_rag/configs 2>/dev/null | head -120
