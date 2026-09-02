"""Create a console-local, gold-free catalog from an explicitly supplied JSONL file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ALLOWED_FIELDS = ("question_id", "question", "source_types", "question_type")


def convert(source: Path) -> list[dict]:
    questions: list[dict] = []
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not all(key in item for key in ("question_id", "question")):
            raise ValueError(f"line {line_number}: question_id and question are required")
        category_values = item.get("question_type") or item.get("source_types") or ["未分类"]
        category = ", ".join(category_values) if isinstance(category_values, list) else str(category_values)
        questions.append({"id": str(item["question_id"]), "category": category, "text": str(item["question"])})
    return questions


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a gold-free console question catalog")
    parser.add_argument("--source", type=Path, required=True, help="Explicit source JSONL path; this script never modifies it")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "questions.public.json")
    args = parser.parse_args()
    if not args.source.is_file():
        raise SystemExit(f"Source not found: {args.source}")
    questions = convert(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"questions": questions}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(questions)} gold-free questions to {args.output}")


if __name__ == "__main__":
    main()
