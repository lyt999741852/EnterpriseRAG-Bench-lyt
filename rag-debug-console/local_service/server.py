"""Serve the archived P0 release locally without importing the active RAG tree."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4


SERVICE_ROOT = Path(__file__).resolve().parent
CONSOLE_ROOT = SERVICE_ROOT.parent
MANIFEST = json.loads((SERVICE_ROOT / "release_manifest.json").read_text(encoding="utf-8"))
DEFAULT_FROZEN_ROOT = CONSOLE_ROOT / "runtime" / "frozen-rag-bge500-p0" / "bge500_rag_pageindex_core"


class FrozenP0Runner:
    def __init__(self, frozen_root: Path):
        self.frozen_root = frozen_root

    def answer(self, question: str, rag_version: str) -> dict:
        if rag_version != MANIFEST["id"]:
            raise ValueError("Requested version is not available in this local sidecar")
        if not self.frozen_root.is_dir():
            raise RuntimeError(f"Frozen P0 archive is missing: {self.frozen_root}")
        request_id = uuid4().hex
        runtime = CONSOLE_ROOT / "runtime" / "local-p0-runs" / request_id
        runtime.mkdir(parents=True, exist_ok=True)
        questions_path = runtime / "questions.jsonl"
        questions_path.write_text(json.dumps({"question_id": f"local_{request_id}", "question": question}) + "\n", encoding="utf-8")
        config_path = runtime / "config.yaml"
        self._write_config(config_path, questions_path, runtime, request_id)
        started = time.monotonic()
        completed = subprocess.run(
            [sys.executable, "-m", "src.pipeline", str(config_path)], cwd=self.frozen_root,
            capture_output=True, text=True, timeout=900, check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("Frozen RAG run failed; inspect isolated runtime logs")
        output = runtime / "outputs" / f"local_p0_{request_id}"
        answer = json.loads((output / "answers.jsonl").read_text(encoding="utf-8").splitlines()[0])
        trace = json.loads((output / "route_trace.jsonl").read_text(encoding="utf-8").splitlines()[0])
        return {"answer": {"text": answer["answer"], "document_ids": answer["document_ids"]}, "trace": trace, "metrics": {"document_recall_pct": None, "invalid_extra_docs": None, "judge": None}, "timing_ms": {"total": round((time.monotonic() - started) * 1000)}}

    def _write_config(self, config_path: Path, questions_path: Path, runtime: Path, request_id: str) -> None:
        import yaml

        source = self.frozen_root / MANIFEST["frozen_config"]
        config = yaml.safe_load(source.read_text(encoding="utf-8"))
        config["questions_file"] = str(questions_path)
        config["output_dir"] = str(runtime / "outputs")
        config["evaluation"] = {"enabled": False}
        config["pipeline"]["name"] = f"local_p0_{request_id}"
        config["pipeline"]["question_parallelism"] = 1
        config["pipeline"]["resume"] = False
        config["pipeline"]["read_existing_index"] = True
        for env_name, target in (("P0_CORPUS_DIR", "corpus_dir"), ("P0_INDEX_DIR", "index_dir")):
            if os.environ.get(env_name):
                config[target] = os.environ[env_name]
        if os.environ.get("P0_INDEX_DIR"):
            config["pageindex"]["manifest_path"] = str(Path(os.environ["P0_INDEX_DIR"]) / "manifest.sqlite3")
        if os.environ.get("P0_PAGEINDEX_HOME"):
            config["pageindex"]["home"] = os.environ["P0_PAGEINDEX_HOME"]
        config_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")


class Handler(BaseHTTPRequestHandler):
    runner: FrozenP0Runner

    def log_message(self, format: str, *args) -> None:  # pragma: no cover
        return

    def _json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/debug/versions":
            fields = ("id", "label", "fingerprint", "published_at", "is_latest")
            self._json(HTTPStatus.OK, {"versions": [{key: MANIFEST[key] for key in fields}]}); return
        self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/debug/answer":
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"}); return
        try:
            length = int(self.headers.get("Content-Length", "0")); payload = json.loads(self.rfile.read(length))
            question = str(payload["question"]).strip()
            if not question: raise ValueError("question is required")
            self._json(HTTPStatus.OK, self.runner.answer(question, str(payload["rag_version"])))
        except (KeyError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--host", default="127.0.0.1"); parser.add_argument("--port", type=int, default=8091); parser.add_argument("--frozen-root", type=Path, default=DEFAULT_FROZEN_ROOT)
    args = parser.parse_args(); Handler.runner = FrozenP0Runner(args.frozen_root); server = ThreadingHTTPServer((args.host, args.port), Handler); print(f"Frozen P0 sidecar: http://{args.host}:{args.port}"); server.serve_forever()


if __name__ == "__main__": main()
