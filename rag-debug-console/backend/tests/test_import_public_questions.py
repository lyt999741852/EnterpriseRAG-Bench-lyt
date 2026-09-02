from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPT_ROOT))
from import_public_questions import convert  # noqa: E402


class PublicQuestionImportTests(unittest.TestCase):
    def test_convert_strips_benchmark_gold_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "questions.jsonl"
            source.write_text('{"question_id":"q1","question":"What?","source_types":["policy"],"gold_answer":"secret","expected_doc_ids":["D1"]}\n', encoding="utf-8")
            self.assertEqual(convert(source), [{"id": "q1", "category": "policy", "text": "What?"}])


if __name__ == "__main__":
    unittest.main()
