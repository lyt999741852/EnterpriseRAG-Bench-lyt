from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.catalog import QuestionCatalog
from backend.app.rag_gateway import MockRagGateway
from backend.app.run_store import RunStore


ROOT = Path(__file__).resolve().parents[2]


class QuestionOnlyContractTests(unittest.TestCase):
    def test_catalog_never_exposes_gold_fields(self) -> None:
        catalog = QuestionCatalog(ROOT / "data" / "catalog.sample.json")
        question = catalog.get("qst_0031")
        self.assertEqual(set(question), {"id", "category", "text"})

    def test_pinned_requires_explicit_published_version(self) -> None:
        gateway = MockRagGateway()
        with self.assertRaisesRegex(ValueError, "requires"):
            gateway.resolve_version("pinned", None)
        version = gateway.resolve_version("pinned", "rag-v2026.08.17-p0")
        self.assertEqual(version.id, "rag-v2026.08.17-p0")

    def test_live_uses_latest_published_version(self) -> None:
        version = MockRagGateway().resolve_version("live", None)
        self.assertTrue(version.is_latest)

    def test_gateway_returns_trace_and_answer_contract(self) -> None:
        gateway = MockRagGateway()
        result = gateway.answer("test", gateway.resolve_version("live", None))
        self.assertEqual(set(result["answer"]), {"text", "document_ids"})
        self.assertIn("retrieval", result["trace"])

    def test_run_store_is_local_and_retrievable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RunStore(Path(temp_dir) / "console.sqlite3")
            result = MockRagGateway().answer("test", MockRagGateway().resolve_version("live", None))
            run = store.create(mode="live", rag_version=result["rag_version"], question={"id": None, "text": "test", "origin": "manual"}, result=result)
            self.assertEqual(store.get(run["run_id"])["question"]["text"], "test")


if __name__ == "__main__":
    unittest.main()
