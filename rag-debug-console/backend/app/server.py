"""Dependency-free HTTP API and static frontend server for the isolated console."""

from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .catalog import QuestionCatalog
from .batch_manager import BatchManager
from .rag_gateway import MockRagGateway
from .run_store import RunStore


APP_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = APP_ROOT / "frontend"
CATALOG_PATH = APP_ROOT / "data" / "questions.public.json"
CATALOG = QuestionCatalog(CATALOG_PATH if CATALOG_PATH.exists() else APP_ROOT / "data" / "catalog.sample.json")
GATEWAY = MockRagGateway()
STORE = RunStore(APP_ROOT / "runtime" / "console.sqlite3")
BATCHES = BatchManager(APP_ROOT / "runtime", APP_ROOT / "data" / "test-suites")


class ConsoleHandler(BaseHTTPRequestHandler):
    server_version = "RagDebugConsole/0.1"

    def log_message(self, format: str, *args) -> None:  # pragma: no cover - normal server noise
        return

    def _json(self, status: HTTPStatus, value: dict | list) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._json(status, {"error": {"message": message}})

    def _request_json(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self._error(HTTPStatus.BAD_REQUEST, "Request body must be valid JSON")
            return None
        if not isinstance(value, dict):
            self._error(HTTPStatus.BAD_REQUEST, "Request body must be a JSON object")
            return None
        return value

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._json(HTTPStatus.OK, {
                "status": "ok", "gateway": "mock", "resource_locks": {"rag-inference": "unlocked", "rag-evaluation": BATCHES.lock_status()},
            })
            return
        if parsed.path == "/api/rag-versions":
            self._json(HTTPStatus.OK, {"versions": GATEWAY.list_versions()})
            return
        if parsed.path == "/api/questions":
            query = parse_qs(parsed.query).get("q", [""])[0]
            self._json(HTTPStatus.OK, {"groups": CATALOG.grouped(query)})
            return
        if parsed.path.startswith("/api/questions/"):
            item = CATALOG.get(parsed.path.rsplit("/", 1)[-1])
            if item is None:
                self._error(HTTPStatus.NOT_FOUND, "Question not found")
            else:
                self._json(HTTPStatus.OK, item)
            return
        if parsed.path == "/api/chat-runs":
            self._json(HTTPStatus.OK, {"runs": STORE.list()})
            return
        if parsed.path == "/api/batch-runs":
            self._json(HTTPStatus.OK, {"runs": BATCHES.list()})
            return
        if parsed.path.startswith("/api/batch-runs/"):
            run = BATCHES.get(parsed.path.rsplit("/", 1)[-1])
            if run is None:
                self._error(HTTPStatus.NOT_FOUND, "Batch run not found")
            else:
                self._json(HTTPStatus.OK, run)
            return
        if parsed.path.startswith("/api/chat-runs/"):
            run = STORE.get(parsed.path.rsplit("/", 1)[-1])
            if run is None:
                self._error(HTTPStatus.NOT_FOUND, "Run not found")
            else:
                self._json(HTTPStatus.OK, run)
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/api/batch-runs/") and path.endswith("/cancel"):
            run = BATCHES.cancel(path.split("/")[-2])
            if run is None:
                self._error(HTTPStatus.NOT_FOUND, "Batch run not found")
            else:
                self._json(HTTPStatus.OK, run)
            return
        if path == "/api/batch-runs":
            payload = self._request_json()
            if payload is None:
                return
            try:
                version = GATEWAY.resolve_version(payload.get("mode", "pinned"), payload.get("rag_version"))
                run = BATCHES.create(str(payload.get("suite", "")), version.__dict__)
            except (ValueError, RuntimeError) as error:
                self._error(HTTPStatus.CONFLICT, str(error))
            else:
                self._json(HTTPStatus.CREATED, run)
            return
        if path != "/api/chat-runs":
            self._error(HTTPStatus.NOT_FOUND, "Endpoint not found")
            return
        payload = self._request_json()
        if payload is None:
            return
        question_id = payload.get("question_id")
        catalog_question = CATALOG.get(question_id) if isinstance(question_id, str) else None
        text = catalog_question["text"] if catalog_question else str(payload.get("question", "")).strip()
        if not text:
            self._error(HTTPStatus.BAD_REQUEST, "question or question_id is required")
            return
        mode = payload.get("mode", "live")
        try:
            version = GATEWAY.resolve_version(mode, payload.get("rag_version"))
        except ValueError as error:
            self._error(HTTPStatus.BAD_REQUEST, str(error))
            return
        question = {
            "id": catalog_question["id"] if catalog_question else None,
            "text": text,
            "origin": "catalog" if catalog_question else "manual",
        }
        run = STORE.create(mode=mode, rag_version=version.__dict__, question=question, result=GATEWAY.answer(text, version))
        self._json(HTTPStatus.CREATED, run)

    def _serve_static(self, requested_path: str) -> None:
        relative = "index.html" if requested_path in ("/", "") else requested_path.lstrip("/")
        target = (FRONTEND_ROOT / relative).resolve()
        if FRONTEND_ROOT not in target.parents or not target.is_file():
            self._error(HTTPStatus.NOT_FOUND, "Page not found")
            return
        content = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the isolated RAG debug console")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), ConsoleHandler)
    print(f"RAG debug console running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
