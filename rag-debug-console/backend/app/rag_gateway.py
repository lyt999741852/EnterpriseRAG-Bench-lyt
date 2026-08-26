"""Versioned, question-only RAG gateway contract and local mock implementation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RagVersion:
    id: str
    label: str
    fingerprint: str
    published_at: str
    is_latest: bool = False


PUBLISHED_VERSIONS = (
    RagVersion(
        id="rag-v2026.08.17-p0",
        label="P0 frozen baseline",
        fingerprint="sha256:4ed33d15b5c8",
        published_at="2026-08-17T12:00:00Z",
    ),
    RagVersion(
        id="rag-v2026.08.26-a34",
        label="A34 published candidate",
        fingerprint="sha256:85aa31cde32f",
        published_at="2026-08-26T09:00:00Z",
        is_latest=True,
    ),
)


class MockRagGateway:
    """A deterministic stand-in until an independently deployed RAG API exists."""

    def list_versions(self) -> list[dict]:
        return [version.__dict__ for version in PUBLISHED_VERSIONS]

    def resolve_version(self, mode: str, requested: str | None) -> RagVersion:
        by_id = {version.id: version for version in PUBLISHED_VERSIONS}
        latest = next(version for version in PUBLISHED_VERSIONS if version.is_latest)
        if mode == "live":
            version = by_id.get(requested) if requested else latest
            if version is None:
                raise ValueError("Unknown published RAG version")
            return version
        if mode == "pinned":
            if not requested:
                raise ValueError("pinned mode requires rag_version")
            version = by_id.get(requested)
            if version is None:
                raise ValueError("pinned mode only accepts a published RAG version")
            return version
        raise ValueError("mode must be pinned or live")

    def answer(self, question: str, version: RagVersion) -> dict:
        """Return trace-shaped mock data without reaching any RAG service or dataset."""
        return {
            "answer": {
                "text": (
                    "Mock response: the production gateway will return the final answer "
                    "from the selected published RAG version."
                ),
                "document_ids": ["DOC-1827", "DOC-4451"],
            },
            "trace": {
                "route": {"type": "semantic", "source": "mock_gateway", "elapsed_ms": 210},
                "retrieval": {"views": ["original_keyword", "original_dense", "rewritten_dense"], "candidate_chunks": 120, "elapsed_ms": 840},
                "rerank": {"input_chunks": 120, "output_chunks": 30, "elapsed_ms": 610},
                "pageindex": {"action": "selected_evidence", "documents_audited": 18, "elapsed_ms": 1200},
                "evidence": {"selected_chunks": 6, "document_ids": ["DOC-1827", "DOC-4451"], "elapsed_ms": 390},
                "generation": {"model": "mock", "elapsed_ms": 450},
            },
            "metrics": {"document_recall_pct": None, "invalid_extra_docs": None, "judge": None},
            "timing_ms": {"total": 3700},
            "rag_version": version.__dict__,
        }
