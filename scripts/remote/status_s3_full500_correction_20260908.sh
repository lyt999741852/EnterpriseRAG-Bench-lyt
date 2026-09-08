#!/usr/bin/env bash
set -euo pipefail
: "${ERAG_APP_DIR:?ERAG_APP_DIR is required}"
CORR="$ERAG_APP_DIR/outputs/s3_repro_full500_20260903/official_correction_dpv4_20260908"
echo "files"
ls -lh "$CORR" 2>/dev/null || true
echo "prepare"
tail -n 8 "$CORR/prepare.log" 2>/dev/null || true
echo "score"
tail -n 12 "$CORR/score.log" 2>/dev/null || true
echo "processes"
pgrep -af 'prepare_official_correction_bundle|metrics_based_eval' || true
