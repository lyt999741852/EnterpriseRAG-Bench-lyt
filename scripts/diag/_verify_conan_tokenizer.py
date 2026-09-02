"""Verify local Conan tokenizer vs vLLM /tokenize consistency.

Downloads TencentBAC/Conan-embedding-v1 tokenizer files, then compares
token counts against the serving /tokenize endpoint on 100 real chunks
sampled from the local cache.
"""
import hashlib
import json
import os
import random
import sys
import urllib.request

TOKENIZER_DIR = os.path.join(".index_cache", "conan_tokenizer")
API = "http://10.72.55.209:7993/v1"
API_KEY = os.environ.get("EMBEDDING_API_KEY", "123456")
FILES = {
    "tokenizer.json": "https://huggingface.co/TencentBAC/Conan-embedding-v1/resolve/main/tokenizer.json",
    "tokenizer_config.json": "https://huggingface.co/TencentBAC/Conan-embedding-v1/resolve/main/tokenizer_config.json",
    "special_tokens_map.json": "https://huggingface.co/TencentBAC/Conan-embedding-v1/resolve/main/special_tokens_map.json",
}
CHUNKS = os.path.join(".index_cache", "full_es_qwen3_emb", "chunks.jsonl")


def fetch(name: str, url: str) -> str:
    path = os.path.join(TOKENIZER_DIR, name)
    if os.path.exists(path):
        return path
    os.makedirs(TOKENIZER_DIR, exist_ok=True)
    print(f"downloading {name} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    with open(path, "wb") as f:
        f.write(data)
    return path


def main() -> int:
    from transformers import AutoTokenizer

    for name, url in FILES.items():
        fetch(name, url)
    tok = AutoTokenizer.from_pretrained(TOKENIZER_DIR, local_files_only=True)

    texts = []
    if os.path.exists(CHUNKS):
        with open(CHUNKS, encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]
        random.seed(42)
        for line in random.sample(lines, min(100, len(lines))):
            texts.append(json.loads(line)["text"])
    if not texts:
        # Fall back to sampling real files from the corpus.
        import glob
        files = glob.glob(os.path.join("corpus", "all_documents", "**", "*.txt"), recursive=True)
        random.seed(42)
        for path in random.sample(files, min(100, len(files))):
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    texts.append(f.read()[:2000])
            except OSError:
                continue
    print(f"sampled {len(texts)} texts")

    mismatches = 0
    max_diff = 0
    for i, text in enumerate(texts[:100]):
        local_len = len(tok.encode(text, add_special_tokens=True))
        body = json.dumps({"model": "embedding", "prompt": text}).encode("utf-8")
        base = API.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        req = urllib.request.Request(
            base + "/tokenize", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {API_KEY}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                remote_len = int(json.loads(resp.read())["count"])
        except Exception as exc:
            print(f"  [{i}] remote error: {exc}")
            mismatches += 1
            continue
        diff = abs(local_len - remote_len)
        max_diff = max(max_diff, diff)
        if diff != 0:
            mismatches += 1
            print(f"  [{i}] local={local_len} remote={remote_len} diff={diff}")
    total = min(100, len(texts))
    print(f"RESULT: {total - mismatches}/{total} exact match, max_diff={max_diff}")
    return 0 if mismatches == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
