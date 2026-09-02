"""Read-only E5 tokenizer audit for a chunks.jsonl file.

Example:
  python scripts/diag/audit_e5_chunks.py \
    --chunks .index_cache/full_es_qwen3_emb_v3_conan448/chunks.jsonl \
    --model /data06/embedding-models/multilingual-e5-large \
    --strict
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve()
ROOT = _SCRIPT_PATH.parents[2] if len(_SCRIPT_PATH.parents) > 2 else _SCRIPT_PATH.parent
sys.path.insert(0, str(ROOT))

try:
    from src.e5_chunk_audit import audit_jsonl, load_tokenizer, write_report  # noqa: E402
except ModuleNotFoundError:
    # Supports a temporary single-file deployment under /tmp for server audit.
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    from e5_chunk_audit import audit_jsonl, load_tokenizer, write_report  # type: ignore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", required=True, help="Input chunks.jsonl")
    parser.add_argument("--model", required=True, help="Local E5 model directory")
    parser.add_argument("--report", help="Optional JSON report path")
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--safety-limit", type=int, default=480)
    parser.add_argument("--recommended-size", type=int, default=384)
    parser.add_argument("--recommended-overlap", type=int, default=64)
    parser.add_argument("--strict", action="store_true", help="Exit 2 if unsafe")
    args = parser.parse_args()

    print("E5_AUDIT_TOKENIZER_LOAD", flush=True)
    report = audit_jsonl(
        args.chunks,
        load_tokenizer(args.model),
        batch_size=args.batch_size,
        max_tokens=args.max_tokens,
        safety_limit=args.safety_limit,
        recommended_size=args.recommended_size,
        recommended_overlap=args.recommended_overlap,
    )
    print("E5_AUDIT_SCAN_COMPLETE", flush=True)
    if args.report:
        write_report(report, args.report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["safe_for_embedding"] or not args.strict else 2


if __name__ == "__main__":
    raise SystemExit(main())
