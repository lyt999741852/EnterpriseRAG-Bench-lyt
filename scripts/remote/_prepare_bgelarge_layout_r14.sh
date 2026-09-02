set -u
DEST=/data06/embedding-models/bge-large-en-v1.5
SMALL=/opt/enterprise-rag-bench/model_cache/hub/models--BAAI--bge-small-en-v1.5/snapshots/5c38ec7c405ec4b44b94cc5a9bb96e735b38267a
mkdir -p "$DEST/1_Pooling"
for f in special_tokens_map.json tokenizer_config.json vocab.txt tokenizer.json; do cp -L "$SMALL/$f" "$DEST/$f"; done
cp -L "$SMALL/sentence_bert_config.json" "$DEST/sentence_bert_config.json"
cp -L "$SMALL/config_sentence_transformers.json" "$DEST/config_sentence_transformers.json"
cp -L "$SMALL/1_Pooling/config.json" "$DEST/1_Pooling/config.json"
python - <<'PY'
import json
dest='/data06/embedding-models/bge-large-en-v1.5'
config={
  'architectures':['BertModel'], 'attention_probs_dropout_prob':0.1,
  'classifier_dropout':None, 'hidden_act':'gelu', 'hidden_dropout_prob':0.1,
  'hidden_size':1024, 'id2label':{'0':'LABEL_0'}, 'initializer_range':0.02,
  'intermediate_size':4096, 'label2id':{'LABEL_0':0}, 'layer_norm_eps':1e-12,
  'max_position_embeddings':512, 'model_type':'bert', 'num_attention_heads':16,
  'num_hidden_layers':24, 'pad_token_id':0, 'position_embedding_type':'absolute',
  'torch_dtype':'float32', 'type_vocab_size':2, 'use_cache':True, 'vocab_size':30522,
}
json.dump(config,open(dest+'/config.json','w'),indent=2)
modules=[
 {'idx':0,'name':'0','path':'','type':'sentence_transformers.models.Transformer'},
 {'idx':1,'name':'1','path':'1_Pooling','type':'sentence_transformers.models.Pooling'},
]
json.dump(modules,open(dest+'/modules.json','w'),indent=2)
pool=json.load(open(dest+'/1_Pooling/config.json'))
pool['word_embedding_dimension']=1024
json.dump(pool,open(dest+'/1_Pooling/config.json','w'),indent=2)
PY
find -L "$DEST" -maxdepth 2 -type f -printf '%f %s\\n' | sort
