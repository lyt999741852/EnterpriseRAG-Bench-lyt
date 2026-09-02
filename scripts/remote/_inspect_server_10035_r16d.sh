set -u
echo '=== OpenAI-compatible model endpoints ==='
for p in 7777 18382 18401 18402 7036; do
  echo "[$p]"
  curl -sS --max-time 6 "http://127.0.0.1:${p}/v1/models" 2>/dev/null | python3 -c 'import json,sys; 
try:
 d=json.load(sys.stdin); print([x.get("id") for x in d.get("data",[])])
except Exception: print("unavailable-or-non-json")' || echo unavailable
done
