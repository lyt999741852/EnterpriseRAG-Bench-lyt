source /root/anaconda3/etc/profile.d/conda.sh
conda activate embedding_test
python - <<'PY'
mods=['onnxruntime','optimum','onnx','torch','transformers','sentence_transformers']
for m in mods:
    try:
        x=__import__(m)
        print(m,getattr(x,'__version__','ok'))
    except Exception as e:
        print(m,'ERR',type(e).__name__,str(e)[:160])
PY
