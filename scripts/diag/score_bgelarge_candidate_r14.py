"""Score an already-built R14 BGE-large candidate index without re-encoding docs."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from urllib.request import Request, urlopen
import numpy as np

QIDS = [
    "qst_0013", "qst_0018", "qst_0022", "qst_0030", "qst_0035", "qst_0041",
    "qst_0050", "qst_0056", "qst_0079", "qst_0082", "qst_0093", "qst_0107",
    "qst_0112", "qst_0116", "qst_0119", "qst_0125", "qst_0154", "qst_0169",
    "qst_0184", "qst_0197", "qst_0211", "qst_0231", "qst_0236", "qst_0241",
    "qst_0251", "qst_0271", "qst_0272", "qst_0280", "qst_0291", "qst_0298",
    "qst_0301", "qst_0322", "qst_0324", "qst_0328", "qst_0341", "qst_0350",
    "qst_0356", "qst_0362", "qst_0386", "qst_0390", "qst_0406", "qst_0413",
    "qst_0416", "qst_0432", "qst_0447", "qst_0459", "qst_0470", "qst_0480",
    "qst_0491", "qst_0498",
]

def get_json(url, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(url, data=data, method=method or ("POST" if payload is not None else "GET"), headers={"Content-Type":"application/json"})
    with urlopen(req, timeout=300) as r: return json.loads(r.read().decode())

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--questions',default='questions.jsonl'); ap.add_argument('--es',default='http://127.0.0.1:9200'); ap.add_argument('--index',default='enterprise-rag-bge-large-r14-candidates50-k40'); ap.add_argument('--small-model',default='/opt/enterprise-rag-bench/model_cache/hub/models--BAAI--bge-small-en-v1.5/snapshots/5c38ec7c405ec4b44b94cc5a9bb96e735b38267a'); ap.add_argument('--large-model',default='/data06/embedding-models/bge-large-en-v1.5'); ap.add_argument('--output',required=True); args=ap.parse_args()
    from sentence_transformers import SentenceTransformer
    qs={r['question_id']:r for r in (json.loads(x) for x in Path(args.questions).read_text(encoding='utf-8').splitlines()) if r.get('question_id')}
    body={'size':10000,'query':{'match_all':{}},'_source':['chunk_id','doc_id','source_type','text','chunk_index','title','embedding']}
    hits=get_json(f"{args.es.rstrip('/')}/{args.index}/_search",body).get('hits',{}).get('hits',[])
    rec=[h.get('_source') or {} for h in hits]; rec=[r for r in rec if r.get('embedding')]
    large_doc=np.asarray([r['embedding'] for r in rec],dtype=np.float32); texts=[str(r.get('text') or '') for r in rec]
    small=SentenceTransformer(args.small_model,device='cpu',local_files_only=True); large=SentenceTransformer(args.large_model,device='cpu',local_files_only=True)
    small_doc=np.asarray(small.encode(texts,batch_size=128,normalize_embeddings=True,show_progress_bar=True),dtype=np.float32)
    rows=[]
    for qid in QIDS:
        q=qs[qid]; expected={str(x) for x in q.get('expected_doc_ids',[]) if x}; qsml=np.asarray(small.encode(q['question'],normalize_embeddings=True),dtype=np.float32); qlrg=np.asarray(large.encode(q['question'],normalize_embeddings=True),dtype=np.float32)
        row={'question_id':qid,'question_type':q.get('question_type'),'expected_doc_ids':sorted(expected)}
        for name, scores in [('bge_small',small_doc@qsml),('bge_large',large_doc@qlrg)]:
            order=np.argsort(-scores); rank=next((i+1 for i in order if str(rec[int(i)].get('doc_id')) in expected),None); row[name+'_rank']=int(rank) if rank is not None else None
        rows.append(row)
    ks=[30,120,240,1000]; summary={n:{str(k):round(sum(r[n+'_rank'] is not None and r[n+'_rank']<=k for r in rows)/len(rows)*100,2) for k in ks} for n in ('bge_small','bge_large')}
    out={'schema_version':1,'scope':'R14 conditional candidate-pool screen; not full-corpus recall','candidate_count':len(rec),'index':args.index,'summary':summary,'rows':rows}; Path(args.output).parent.mkdir(parents=True,exist_ok=True); Path(args.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
