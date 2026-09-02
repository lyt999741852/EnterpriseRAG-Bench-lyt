from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from backend.app.rag_gateway import PublishedRagGateway


class PublishedGatewayTests(unittest.TestCase):
    @patch("backend.app.rag_gateway.urlopen")
    def test_published_gateway_preserves_debug_contract(self, mocked_open: MagicMock) -> None:
        response = MagicMock()
        response.read.return_value = json.dumps({"answer": {"text": "ok", "document_ids": []}, "trace": {}, "metrics": {}, "timing_ms": {"total": 1}}).encode()
        mocked_open.return_value.__enter__.return_value = response
        gateway = PublishedRagGateway("http://published-rag")
        from backend.app.rag_gateway import RagVersion
        result = gateway.answer("question-only", RagVersion("rag-v1", "V1", "sha256:x", "2026-01-01T00:00:00Z"))
        self.assertEqual(result["answer"]["text"], "ok")
        request = mocked_open.call_args.args[0]
        self.assertEqual(json.loads(request.data)["question"], "question-only")


if __name__ == "__main__":
    unittest.main()
