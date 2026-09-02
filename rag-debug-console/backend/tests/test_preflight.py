from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from preflight_published_rag import preflight  # noqa: E402


class FakeGateway:
    def list_versions(self):
        return [{"id": "rag-v1"}]

    def resolve_version(self, mode, requested):
        return SimpleNamespace(id="rag-v1")

    def answer(self, question, version):
        return {"answer": {"text": "ok", "document_ids": ["DOC-1"]}, "trace": {"retrieval": {}}, "metrics": {"document_recall_pct": 100}, "timing_ms": {"total": 100}}


class PreflightTests(unittest.TestCase):
    def test_preflight_checks_only_question_contract(self) -> None:
        result = preflight(FakeGateway(), "question-only probe", "rag-v1")
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["document_count"], 1)


if __name__ == "__main__":
    unittest.main()
