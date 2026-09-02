set -u
echo '--- docker containers ---'
docker ps --format '{{.ID}} {{.Names}} {{.Image}} {{.Ports}}' 2>/dev/null | head -80 || true
echo '--- top-level data dirs ---'
for d in /data /data01 /data06 /model /models /opt/ollama/models; do
  if [ -e "$d" ]; then du -sh "$d" 2>/dev/null; ls -ld "$d"; fi
done
echo '--- model names in likely roots ---'
find /data /data01 /data06 /model /models /opt/ollama/models -maxdepth 3 -type f 2>/dev/null | grep -Ei 'config.json|model.*safetensors|pytorch_model|tokenizer' | head -120 || true
echo '--- all listening TCP ---'
ss -lntp 2>/dev/null | head -120 || true
echo '--- vLLM command lines (ports/api keys omitted) ---'
ps -eo pid,cmd 2>/dev/null | grep -E '[v]llm serve|[v]llm.entrypoints' | sed -E 's/--api-key [^ ]+ /--api-key REDACTED /g' | head -60 || true
