set -u
base=/data01/.cache/home/hub/models--BAAI--bge-m3/snapshots/5617a9f61b028005a4858fdac845db406aefb181
echo '=== ONNX FILES ==='
find "$base/onnx" -maxdepth 2 -type f -printf '%f %s bytes\n' 2>/dev/null | head -30 || true
echo '=== ONNX RUNTIME ==='
python3 - <<'PY'
try:
 import onnxruntime as ort
 print('onnxruntime',ort.__version__,ort.get_available_providers())
except Exception as e: print('onnxruntime_unavailable',type(e).__name__,str(e)[:200])
PY
