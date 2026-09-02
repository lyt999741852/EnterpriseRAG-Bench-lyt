"""Prepare the minimal official document bundle needed by correction scoring.

The upstream evaluator loads raw JSON documents through
``generated_data/uuid_index.json``.  Normal retrieval experiments only need the
exported TXT corpus, so the server intentionally does not keep all 500k raw
JSON files.  This helper downloads only the documents referenced by the
selected questions and answer rows, preserving their official relative paths.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


DEFAULT_RAW_ROOT = (
    "https://raw.githubusercontent.com/onyx-dot-app/"
    "EnterpriseRAG-Bench/main/generated_data"
)


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(row)
    return rows


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def write_jsonl_atomic(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def download_bytes(url: str, attempts: int = 3, timeout: int = 120) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = Request(url, headers={"User-Agent": "EnterpriseRAG-Bench"})
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:  # network failures are retried with backoff
            last_error = exc
            if attempt < attempts:
                time.sleep(2 ** (attempt - 1))
    assert last_error is not None
    raise last_error


def ensure_uuid_index(path: Path, raw_root: str) -> dict[str, str]:
    if not path.exists():
        print(f"Downloading official UUID index -> {path}")
        payload = download_bytes(f"{raw_root.rstrip('/')}/uuid_index.json")
        parsed = json.loads(payload.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("Official UUID index was not a JSON object")
        write_json_atomic(path, parsed)

    with path.open(encoding="utf-8") as stream:
        parsed = json.load(stream)
    if not isinstance(parsed, dict):
        raise ValueError(f"UUID index at {path} was not a JSON object")
    return {str(key): str(value) for key, value in parsed.items()}


def valid_cached_document(path: Path, expected_doc_id: str) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
        return isinstance(value, dict) and value.get("dataset_doc_uuid") == expected_doc_id
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions-file", required=True)
    parser.add_argument("--answers-file", required=True)
    parser.add_argument("--official-root", required=True)
    parser.add_argument("--bundle-dir", required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--raw-root", default=DEFAULT_RAW_ROOT)
    args = parser.parse_args()

    questions_file = Path(args.questions_file).resolve()
    answers_file = Path(args.answers_file).resolve()
    official_root = Path(args.official_root).resolve()
    bundle_dir = Path(args.bundle_dir).resolve()
    sources_dir = official_root / "generated_data" / "sources"
    full_uuid_index_path = official_root / "generated_data" / "uuid_index.json"

    questions = load_jsonl(questions_file)
    answers = load_jsonl(answers_file)
    answer_ids = [str(row.get("question_id", "")) for row in answers]
    if any(not question_id for question_id in answer_ids):
        raise ValueError("Every answer row must contain question_id")
    if len(answer_ids) != len(set(answer_ids)):
        raise ValueError("Answers contain duplicate question_id values")

    questions_by_id = {
        str(row.get("question_id", "")): row
        for row in questions
        if row.get("question_id")
    }
    missing_questions = sorted(set(answer_ids) - questions_by_id.keys())
    if missing_questions:
        raise ValueError(
            f"Answers reference {len(missing_questions)} unknown questions: "
            + ", ".join(missing_questions[:10])
        )

    selected_id_set = set(answer_ids)
    selected_questions = [
        row for row in questions if row.get("question_id") in selected_id_set
    ]
    selected_questions_path = bundle_dir / "questions.jsonl"
    write_jsonl_atomic(selected_questions_path, selected_questions)

    needed_doc_ids: set[str] = set()
    for row in selected_questions:
        needed_doc_ids.update(str(item) for item in row.get("expected_doc_ids", []))
    for row in answers:
        needed_doc_ids.update(str(item) for item in row.get("document_ids", []))
    needed_doc_ids.discard("")

    uuid_index = ensure_uuid_index(full_uuid_index_path, args.raw_root)
    missing_paths = sorted(needed_doc_ids - uuid_index.keys())
    if missing_paths:
        raise ValueError(
            f"Official UUID index is missing {len(missing_paths)} document IDs: "
            + ", ".join(missing_paths[:10])
        )

    filtered_index = {
        doc_id: uuid_index[doc_id] for doc_id in sorted(needed_doc_ids)
    }
    filtered_index_path = bundle_dir / "uuid_index.json"
    write_json_atomic(filtered_index_path, filtered_index)

    pending = [
        doc_id
        for doc_id, relative_path in filtered_index.items()
        if not valid_cached_document(sources_dir / relative_path, doc_id)
    ]
    print(
        f"Selected questions={len(selected_questions)} answers={len(answers)} "
        f"documents={len(filtered_index)} cached={len(filtered_index) - len(pending)} "
        f"pending={len(pending)}"
    )

    def fetch_document(doc_id: str) -> tuple[str, int]:
        relative_path = filtered_index[doc_id]
        encoded_path = quote(relative_path.replace("\\", "/"), safe="/")
        url = f"{args.raw_root.rstrip('/')}/sources/{encoded_path}"
        payload = download_bytes(url)
        parsed = json.loads(payload.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError(f"{doc_id}: downloaded document was not an object")
        if parsed.get("dataset_doc_uuid") != doc_id:
            raise ValueError(
                f"{doc_id}: downloaded dataset_doc_uuid="
                f"{parsed.get('dataset_doc_uuid')!r}"
            )
        destination = sources_dir / relative_path
        write_json_atomic(destination, parsed)
        return doc_id, len(payload)

    downloaded_bytes = 0
    workers = max(1, int(args.workers))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_document, doc_id): doc_id for doc_id in pending}
        for completed, future in enumerate(as_completed(futures), 1):
            doc_id, size = future.result()
            downloaded_bytes += size
            if completed % 25 == 0 or completed == len(pending):
                print(
                    f"Downloaded {completed}/{len(pending)} documents "
                    f"({downloaded_bytes / 1024 / 1024:.1f} MiB)"
                )

    invalid_after = [
        doc_id
        for doc_id, relative_path in filtered_index.items()
        if not valid_cached_document(sources_dir / relative_path, doc_id)
    ]
    if invalid_after:
        raise RuntimeError(
            f"Document validation failed for {len(invalid_after)} IDs: "
            + ", ".join(invalid_after[:10])
        )

    manifest = {
        "questions_file": str(selected_questions_path),
        "answers_file": str(answers_file),
        "uuid_index_file": str(filtered_index_path),
        "question_count": len(selected_questions),
        "document_count": len(filtered_index),
        "downloaded_count": len(pending),
        "raw_root": args.raw_root,
    }
    write_json_atomic(bundle_dir / "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
