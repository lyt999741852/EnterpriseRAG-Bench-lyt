"""Verify a separately deployed RAG debug service before connecting the console."""

from __future__ import annotations

import argparse
import json
import sys

from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from backend.app.rag_gateway import PublishedRagGateway  # noqa: E402


def preflight(gateway: PublishedRagGateway, question: str, requested_version: str | None) -> dict:
    versions = gateway.list_versions()
    if not versions:
        raise ValueError("Published RAG service has no published versions")
    version = gateway.resolve_version("pinned" if requested_version else "live", requested_version)
    result = gateway.answer(question, version)
    document_ids = result.get("answer", {}).get("document_ids")
    if not isinstance(document_ids, list):
        raise ValueError("Published RAG service answer.document_ids must be a list")
    return {
        "status": "passed",
        "gateway_versions": len(versions),
        "selected_version": version.__dict__,
        "trace_stages": sorted(result["trace"]),
        "has_metrics": bool(result["metrics"]),
        "document_count": len(document_ids),
        "timing_ms": result["timing_ms"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight a published RAG debug service")
    parser.add_argument("--base-url", required=True, help="Independent RAG debug service URL")
    parser.add_argument("--question", required=True, help="Question-only smoke probe; do not pass gold answers")
    parser.add_argument("--rag-version", help="Published fixed version; omit to test latest published version")
    args = parser.parse_args()
    try:
        result = preflight(PublishedRagGateway(args.base_url), args.question, args.rag_version)
    except (RuntimeError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
