set -u
echo '=== HOST ==='
hostname
base=/data01/.cache/home/hub/models--BAAI--bge-m3
echo '=== CACHE ==='
if [ -d "$base" ]; then
  du -sh "$base" 2>/dev/null || true
  find "$base" -maxdepth 2 -type f -printf '%p %s bytes\n' 2>/dev/null | head -80 || true
  echo '-- refs --'
  for f in "$base"/refs/*; do [ -f "$f" ] && { echo "$f"; cat "$f"; }; done
else
  echo 'cache-missing'
fi
echo '=== SNAPSHOTS ==='
find "$base/snapshots" -maxdepth 2 -type f -printf '%p %s bytes\n' 2>/dev/null | head -100 || true
echo '=== PYTHON PACKAGES ==='
python3 - <<'PY'
for name in ('torch','transformers','sentence_transformers'):
 try:
  m=__import__(name); print(name, getattr(m,'__version__','ok'))
 except Exception as e: print(name,'UNAVAILABLE',type(e).__name__,str(e)[:160])
PY
