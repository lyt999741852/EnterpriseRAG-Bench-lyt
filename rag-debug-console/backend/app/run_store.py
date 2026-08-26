"""Local SQLite persistence for console runs. Writes stay under rag-debug-console/runtime."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


class RunStore:
    def __init__(self, database_path: Path):
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._database_path = database_path
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS chat_runs (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL,
                    mode TEXT NOT NULL, rag_version TEXT NOT NULL, question_json TEXT NOT NULL,
                    result_json TEXT NOT NULL
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def create(self, *, mode: str, rag_version: str, question: dict, result: dict) -> dict:
        run = {
            "run_id": f"chat_{uuid4().hex[:12]}",
            "created_at": datetime.now(UTC).isoformat(),
            "status": "completed",
            "mode": mode,
            "rag_version": rag_version,
            "question": question,
            **result,
        }
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT INTO chat_runs VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    run["run_id"], run["created_at"], run["status"], run["mode"], run["rag_version"]["id"],
                    json.dumps(question), json.dumps(result),
                ),
            )
        return run

    def get(self, run_id: str) -> dict | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute("SELECT * FROM chat_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        result = json.loads(row["result_json"])
        return {
            "run_id": row["id"], "created_at": row["created_at"], "status": row["status"],
            "mode": row["mode"], "rag_version": result["rag_version"],
            "question": json.loads(row["question_json"]), **result,
        }

    def list(self) -> list[dict]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute("SELECT * FROM chat_runs ORDER BY created_at DESC").fetchall()
        return [
            {
                "run_id": row["id"], "created_at": row["created_at"], "status": row["status"],
                "mode": row["mode"], "rag_version": row["rag_version"], "question": json.loads(row["question_json"]),
            }
            for row in rows
        ]
