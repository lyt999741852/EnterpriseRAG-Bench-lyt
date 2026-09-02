set -u
echo '--- LOCAL ELASTICSEARCH INDICES ---'
curl -fsS --max-time 20 'http://127.0.0.1:9200/_cat/indices?h=health,status,index,docs.count,store.size' || true
echo
echo '--- LOCAL VECTOR MAPPINGS ---'
for index in enterprise-rag-bge-small-v1 enterprise-rag-e5-large-v1; do
  echo "INDEX=$index"
  curl -fsS --max-time 15 "http://127.0.0.1:9200/$index/_mapping" \
    | /root/anaconda3/bin/python -c 'import json,sys; d=json.load(sys.stdin); p=next(iter(d.values()))["mappings"]["properties"]; print({"embedding_dims":p.get("embedding",{}).get("dims"),"model_field":p.get("embedding_model",{}).get("type")})' \
    || true
done
echo '--- QWEN REMOTE ES ---'
curl -fsS --max-time 15 'http://10.72.100.29:31920/_cat/indices?h=health,status,index,docs.count,store.size' || true
echo
echo '--- MODEL ASSETS ---'
for model in \
  /data06/embedding-models/multilingual-e5-large \
  /root/.cache/huggingface/hub/models--BAAI--bge-small-en-v1.5; do
  if [ -d "$model" ]; then echo "PRESENT $model"; else echo "MISSING $model"; fi
done
echo '--- EMBEDDING API ---'
curl -fsS --max-time 20 'http://10.72.55.209:7993/v1/embeddings' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer 123456' \
  -d '{"model":"embedding","input":"inventory probe"}' \
  | /root/anaconda3/bin/python -c 'import json,sys; d=json.load(sys.stdin); print({"dimension":len(d.get("data",[{}])[0].get("embedding",[])),"error":d.get("error")})' || true
