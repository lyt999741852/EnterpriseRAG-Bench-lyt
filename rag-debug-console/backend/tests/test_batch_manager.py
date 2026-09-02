from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.batch_manager import BatchManager
from backend.app.rag_gateway import MockRagGateway


ROOT = Path(__file__).resolve().parents[2]


class BatchManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.version = MockRagGateway().resolve_version("pinned", "rag-v2026.08.17-p0").__dict__

    def test_daily_suite_uses_the_repeated_balanced_50_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = BatchManager(Path(temp_dir), ROOT / "data" / "test-suites")
            run = manager.create("daily-50.v1", self.version)
            self.assertEqual(run["total"], 50)
            self.assertEqual(run["suite"], "daily-50.v1")
            manager.cancel(run["run_id"])

    def test_full_suite_requires_exactly_500_imported_questions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = BatchManager(Path(temp_dir), ROOT / "data" / "test-suites")
            with self.assertRaisesRegex(ValueError, "requires importing"):
                manager.create("full-500", self.version)


if __name__ == "__main__":
    unittest.main()
