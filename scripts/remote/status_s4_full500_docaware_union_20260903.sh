#!/usr/bin/env bash
set -euo pipefail
RUN=/opt/enterprise-rag-bench/app/outputs/s4_full500_docaware_union_20260903
echo '--- files ---'
ls -lh "$RUN" 2>/dev/null || true
echo '--- retrieval tail ---'
tail -n 5 "$RUN/retrieval.log" 2>/dev/null || true
echo '--- generation tail ---'
tail -n 5 "$RUN/generation.log" 2>/dev/null || true
echo '--- score tail ---'
tail -n 10 "$RUN/official_score/score.log" 2>/dev/null || true
