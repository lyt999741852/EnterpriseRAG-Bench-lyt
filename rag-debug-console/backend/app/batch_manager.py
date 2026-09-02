"""Independent mock batch queue. It never invokes the repository's RAG pipeline."""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


class BatchManager:
    def __init__(self, runtime_root: Path, suite_root: Path):
        self._runtime_root, self._suite_root = runtime_root, suite_root
        self._lock = threading.Lock()
        self._runs: dict[str, dict] = {}
        self._active_run_id: str | None = None

    def lock_status(self) -> str:
        with self._lock:
            return "locked" if self._active_run_id else "unlocked"

    def create(self, suite: str, rag_version: dict) -> dict:
        question_ids = self._question_ids(suite)
        with self._lock:
            if self._active_run_id:
                raise RuntimeError("rag-evaluation is locked by another batch run")
            run_id = f"batch_{uuid4().hex[:12]}"
            run = {"run_id": run_id, "suite": suite, "created_at": datetime.now(UTC).isoformat(), "status": "queued", "total": len(question_ids), "completed": 0, "failed": 0, "cancel_requested": False, "rag_version": rag_version, "metrics": None}
            self._runs[run_id] = run
            self._active_run_id = run_id
            self._write(run)
        threading.Thread(target=self._execute, args=(run_id,), daemon=True).start()
        return self._snapshot(run)

    def get(self, run_id: str) -> dict | None:
        with self._lock:
            run = self._runs.get(run_id)
            return self._snapshot(run) if run else None

    def list(self) -> list[dict]:
        with self._lock:
            return [self._snapshot(run) for run in sorted(self._runs.values(), key=lambda value: value["created_at"], reverse=True)]

    def cancel(self, run_id: str) -> dict | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            run["cancel_requested"] = True
            self._write(run)
            return self._snapshot(run)

    def _question_ids(self, suite: str) -> list[str]:
        if suite == "daily-50.v1":
            return json.loads((self._suite_root / "daily-50.v1.json").read_text(encoding="utf-8"))["question_ids"]
        if suite == "full-500":
            catalog = self._suite_root.parent / "questions.public.json"
            if not catalog.exists():
                raise ValueError("full-500 requires importing a console-local 500-question public catalog first")
            question_ids = [item["id"] for item in json.loads(catalog.read_text(encoding="utf-8"))["questions"]]
            if len(question_ids) != 500:
                raise ValueError("full-500 requires exactly 500 imported public questions")
            return question_ids
        raise ValueError("suite must be daily-50.v1 or full-500")

    def _execute(self, run_id: str) -> None:
        with self._lock:
            run = self._runs[run_id]
            run["status"] = "running"
            self._write(run)
        while True:
            time.sleep(0.04)
            with self._lock:
                run = self._runs[run_id]
                if run["cancel_requested"]:
                    run["status"] = "cancelled"
                    self._active_run_id = None
                    self._write(run)
                    return
                run["completed"] += 1
                if run["completed"] >= run["total"]:
                    run["status"] = "completed"
                    run["metrics"] = {"overall_pct": None, "document_recall_pct": None, "judge": None, "note": "Mock batch complete; metrics arrive only from a published RAG/evaluation service."}
                    self._active_run_id = None
                self._write(run)
                if run["status"] == "completed":
                    return

    def _write(self, run: dict) -> None:
        target = self._runtime_root / "batches" / run["run_id"] / "run.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self._snapshot(run), ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _snapshot(run: dict | None) -> dict:
        return {key: value for key, value in run.items() if key != "cancel_requested"} if run else {}
