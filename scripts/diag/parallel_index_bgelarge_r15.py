"""Parallel CPU BGE-large encoder and resumable Elasticsearch bulk writer."""
from __future__ import annotations
import argparse, json, os, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

_MODEL = None
_BATCH = 128

def call(url, payload=None, method=None, timeout=300):
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(url, data=data, method=method or ("POST" if payload is not None else "GET"), headers={"Content-Type":"application/json"})
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode()) if response.readable() else {}

def init_worker(model_path: str, batch: int, threads: int):
    global _MODEL, _BATCH
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("OMP_NUM_THREADS", str(threads))
    os.environ.setdefault("MKL_NUM_THREADS", str(threads))
    os.environ.setdefault("OPENBLAS_NUM_THREADS", str(threads))
    import torch
    torch.set_num_threads(threads)
    torch.set_num_interop_threads(1)
    from sentence_transformers import SentenceTransformer
    _MODEL = SentenceTransformer(model_path, device="cpu", local_files_only=True)
    _BATCH = batch

def encode_batch(items):
    texts = [x["text"] for x in items]
    vectors = _MODEL.encode(texts, batch_size=_BATCH, normalize_embeddings=True, show_progress_bar=False)
    return [(items[i], vectors[i].tolist()) for i in range(len(items))]

def iter_windows(path: Path, start: int, window: int):
    with path.open(encoding="utf-8") as handle:
        for _ in range(start):
            if not handle.readline(): return
        while True:
            rows=[]
            for _ in range(window):
                line=handle.readline()
                if not line: break
                rows.append(json.loads(line))
            if not rows: break
            yield rows

def bulk(es: str, index: str, rows):
    lines=[]
    for chunk, vector in rows:
        lines.append(json.dumps({"index":{"_index":index,"_id":chunk["chunk_id"]}},separators=(",",":")))
        doc={"chunk_id":chunk["chunk_id"],"doc_id":chunk["doc_id"],"source_type":chunk["source_type"],"text":chunk["text"],"chunk_index":int(chunk.get("chunk_index",0)),"char_start":int(chunk.get("char_start",0)),"char_end":int(chunk.get("char_end",0)),"embedding_model":"/data06/embedding-models/bge-large-en-v1.5","embedding":vector}
        lines.append(json.dumps(doc,ensure_ascii=False,separators=(",",":")))
    req=Request(f"{es.rstrip('/')}/_bulk",data=("\n".join(lines)+"\n").encode(),method="POST",headers={"Content-Type":"application/x-ndjson"})
    with urlopen(req,timeout=600) as response: result=json.loads(response.read().decode())
    if result.get("errors"):
        errors=[x for x in result.get("items",[]) if int(x.get("index",{}).get("status",500))>=300][:3]
        raise RuntimeError(f"bulk errors: {errors}")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--chunks",required=True); ap.add_argument("--es",default="http://10.72.55.201:31920"); ap.add_argument("--index",default="enterprise-rag-bge-large-en-v1-448-32"); ap.add_argument("--alias",default="enterprise-rag-bge-large-en-v1-448-32-alias"); ap.add_argument("--model",default="/data06/embedding-models/bge-large-en-v1.5"); ap.add_argument("--workers",type=int,default=8); ap.add_argument("--threads",type=int,default=8); ap.add_argument("--batch",type=int,default=128); ap.add_argument("--window",type=int,default=1024); ap.add_argument("--progress",required=True); args=ap.parse_args()
    es=args.es.rstrip("/"); index=args.index
    definition={"aliases":{args.alias:{}},"settings":{"number_of_shards":8,"number_of_replicas":0,"refresh_interval":"-1","index.translog.durability":"async"},"mappings":{"dynamic":"strict","properties":{"chunk_id":{"type":"keyword"},"doc_id":{"type":"keyword"},"source_type":{"type":"keyword"},"text":{"type":"text"},"chunk_index":{"type":"integer"},"char_start":{"type":"integer"},"char_end":{"type":"integer"},"embedding_model":{"type":"keyword"},"embedding":{"type":"dense_vector","dims":1024,"index":True,"similarity":"cosine"}}}}
    try: call(f"{es}/{index}",definition,method="PUT")
    except Exception:
        mapping=call(f"{es}/{index}/_mapping")
        dims=mapping[index]["mappings"]["properties"]["embedding"]["dims"]
        if int(dims)!=1024: raise
    progress=Path(args.progress); start=0
    if progress.exists():
        try: start=int(json.loads(progress.read_text()).get("next_offset",0))
        except Exception: start=0
    chunks=Path(args.chunks); total=sum(1 for _ in chunks.open(encoding="utf-8")); started=time.time(); done=start
    with ProcessPoolExecutor(max_workers=args.workers, initializer=init_worker, initargs=(args.model,args.batch,args.threads)) as pool:
        for window_rows in iter_windows(chunks,start,args.window):
            groups=[window_rows[i:i+args.batch] for i in range(0,len(window_rows),args.batch)]
            futures=[pool.submit(encode_batch,g) for g in groups]
            encoded=[]
            for future in futures: encoded.extend(future.result())
            bulk(es,index,encoded); done += len(window_rows)
            progress.parent.mkdir(parents=True,exist_ok=True); progress.write_text(json.dumps({"next_offset":done,"total":total,"updated_at":time.strftime('%Y-%m-%dT%H:%M:%S%z')},indent=2)+"\n")
            elapsed=max(time.time()-started,1); print(f"INDEX {done}/{total} ({done/total*100:.2f}%) rate={(done-start)/elapsed:.1f}/s",flush=True)
    call(f"{es}/{index}/_settings",{"index":{"refresh_interval":"30s","translog.durability":"request"}})
    call(f"{es}/{index}/_refresh",method="POST")
    print(json.dumps({"index":index,"total":total,"completed":done,"elapsed_seconds":round(time.time()-started,1)},ensure_ascii=False))

if __name__=="__main__": main()
