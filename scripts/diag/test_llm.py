"""Quick test: internal Qwen3.5-27B API connectivity."""
import json
import urllib.request

API_BASE = "http://10.72.100.35:7777/v1"
API_KEY = "lark"
MODEL = "lark"

# Test 1: check /models endpoint
print("=== Test 1: /models ===")
try:
    req = urllib.request.Request(f"{API_BASE}/models")
    req.add_header("Authorization", f"Bearer {API_KEY}")
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read())
    print(f"OK - {len(data.get('data',[]))} models available")
    for m in data.get("data", [])[:5]:
        print(f"  - {m.get('id', '?')}")
except Exception as e:
    print(f"FAIL: {e}")

# Test 2: chat completion
print("\n=== Test 2: Chat Completion ===")
payload = json.dumps({
    "model": MODEL,
    "messages": [
        {"role": "user", "content": "Reply with exactly: OK"}
    ],
    "max_tokens": 50,
    "temperature": 0.0,
}).encode("utf-8")

try:
    req = urllib.request.Request(f"{API_BASE}/chat/completions", data=payload)
    req.add_header("Authorization", f"Bearer {API_KEY}")
    req.add_header("Content-Type", "application/json")
    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read())
    answer = result["choices"][0]["message"]["content"]
    print(f"Response: {answer}")
    print("OK - API works!")
except Exception as e:
    print(f"FAIL: {e}")

print("\n=== Done ===")
