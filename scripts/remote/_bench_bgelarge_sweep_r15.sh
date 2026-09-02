cd /opt/enterprise-rag-bench/app
for n in 16 32 48 64; do
  echo TEST $n
  THREADS=$n bash /opt/enterprise-rag-bench/app/_bench_bgelarge_one_r15.sh
done
