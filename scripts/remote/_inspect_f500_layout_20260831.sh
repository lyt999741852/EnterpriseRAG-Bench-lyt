set -u
RUN=/opt/enterprise-rag-bench/app/outputs/pageindex_full500_bge_dpv4_20260831
echo "RUN=$RUN"
echo '=== TOP LEVEL ==='
find "$RUN" -maxdepth 1 -type f -printf '%f %s bytes\n' | sort
echo '=== SUBDIRECTORIES ==='
find "$RUN" -maxdepth 2 -type f -printf '%P %s bytes\n' | sort | head -120
echo '=== PROJECT INPUTS ==='
for f in /opt/enterprise-rag-bench/app/questions.jsonl /opt/enterprise-rag-bench/app/corpus/all_documents; do
  if [ -e "$f" ]; then echo "$f exists"; else echo "$f missing"; fi
done
