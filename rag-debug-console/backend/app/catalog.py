"""Question catalog. This module intentionally contains no benchmark gold fields."""

from __future__ import annotations

import json
from pathlib import Path


class QuestionCatalog:
    def __init__(self, path: Path):
        self._questions = json.loads(path.read_text(encoding="utf-8"))["questions"]
        self._by_id = {item["id"]: item for item in self._questions}

    def list(self, query: str = "") -> list[dict]:
        needle = query.strip().lower()
        if not needle:
            return self._questions
        return [
            item for item in self._questions
            if needle in item["id"].lower()
            or needle in item["text"].lower()
            or needle in item["category"].lower()
        ]

    def get(self, question_id: str) -> dict | None:
        return self._by_id.get(question_id)

    def grouped(self, query: str = "") -> list[dict]:
        groups: dict[str, list[dict]] = {}
        for question in self.list(query):
            groups.setdefault(question["category"], []).append(question)
        return [
            {"category": name, "questions": values}
            for name, values in groups.items()
        ]
