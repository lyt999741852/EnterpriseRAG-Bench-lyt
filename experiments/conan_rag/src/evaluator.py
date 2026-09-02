"""
Evaluator: wraps the official metrics_based_eval.py script.
Outputs results.json and the submission JSONL for the official eval.

The official script expects:
  - A questions JSONL file (with question_id, gold_answer, answer_facts, expected_doc_ids)
  - An answers JSONL file (with question_id, answer, document_ids)
  - Produces results.json with correctness / completeness / recall / invalid_docs
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EvalResult:
    question_id: str

    # Correctness
    answer_correct: bool
    correctness_reasoning: str = ""

    # Completeness (0-1)
    completeness_pct: float = 0.0

    # Document recall (0-1)
    document_recall_pct: float | None = None

    # Invalid extra documents
    invalid_extra_docs: int | None = None


def load_questions(questions_file: str) -> dict[str, dict]:
    """Load questions JSONL into a dict keyed by question_id."""
    questions = {}
    with open(questions_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            q = json.loads(line)
            questions[q["question_id"]] = q
    return questions


def filter_questions_by_source(
    questions: dict[str, dict],
    source_types: list[str],
    mode: str = "exact",
) -> dict[str, dict]:
    """Filter questions by source.

    ``exact`` selects questions whose complete source set matches the filter;
    ``contains`` preserves the previous intersection behavior.
    """
    if not source_types:
        return questions
    source_set = set(source_types)
    if mode == "exact":
        return {
            qid: q for qid, q in questions.items()
            if set(q.get("source_types", [])) == source_set
        }
    if mode != "contains":
        raise ValueError(f"Unknown source filter mode: {mode}")
    return {
        qid: q for qid, q in questions.items()
        if source_set.intersection(q.get("source_types", []))
    }


def write_answers_jsonl(
    answers: list[dict],
    output_path: str,
):
    """Atomically write answers in the official JSONL format."""
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    temp_path = f"{output_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        for a in answers:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_path, output_path)


def load_answers_jsonl(answers_file: str) -> list[dict]:
    """Load an existing answer checkpoint, ignoring blank lines."""
    answers = []
    if not os.path.exists(answers_file):
        return answers
    with open(answers_file, encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                answers.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"Invalid JSON in {answers_file} at line {line_number}: {e}"
                ) from e
    return answers


def is_failed_answer(answer: dict) -> bool:
    """Return True for empty or machine-detectable LLM failure answers."""
    text = answer.get("answer")
    return not isinstance(text, str) or not text.strip() or text.startswith("[LLM_ERROR:")


def validate_answers(
    answers: list[dict],
    expected_question_ids: set[str] | None = None,
    max_document_ids: int = 10,
) -> list[str]:
    """Validate submission structure and return human-readable errors."""
    errors: list[str] = []
    seen: set[str] = set()
    for index, answer in enumerate(answers, 1):
        qid = answer.get("question_id")
        if not isinstance(qid, str) or not qid:
            errors.append(f"row {index}: missing question_id")
            continue
        if qid in seen:
            errors.append(f"row {index}: duplicate question_id {qid}")
        seen.add(qid)

        if is_failed_answer(answer):
            errors.append(f"{qid}: answer is empty or contains an LLM error")

        doc_ids = answer.get("document_ids")
        if not isinstance(doc_ids, list):
            errors.append(f"{qid}: document_ids must be a list")
            continue
        if len(doc_ids) > max_document_ids:
            errors.append(f"{qid}: more than {max_document_ids} document_ids")
        if any(not isinstance(doc_id, str) or not doc_id for doc_id in doc_ids):
            errors.append(f"{qid}: document_ids contains an invalid value")
        if len(doc_ids) != len(set(doc_ids)):
            errors.append(f"{qid}: document_ids contains duplicates")

    if expected_question_ids is not None:
        missing = expected_question_ids - seen
        unexpected = seen - expected_question_ids
        if missing:
            errors.append(f"missing question_ids: {len(missing)}")
        if unexpected:
            errors.append(f"unexpected question_ids: {len(unexpected)}")
    return errors


def run_official_eval(
    questions_file: str,
    answers_file: str,
    output_dir: str,
    no_correction: bool = True,
    parallelism: int = 8,
    timeout: int = 3600,
    resume: bool = True,
) -> dict:
    """
    Run the official metrics_based_eval.py script.
    Returns the parsed results.json dict.

    The official script is cloned from:
      https://github.com/onyx-dot-app/EnterpriseRAG-Bench
    It lives under llm_answer/ submodule or a local copy.
    """
    # Look for the official eval script in common locations
    eval_script = _find_eval_script()

    if not eval_script:
        print("[WARNING] Official eval script not found. Skipping automated eval.")
        print("  Clone it from: https://github.com/onyx-dot-app/EnterpriseRAG-Bench")
        print("  Then place under: eval/ or llm_answer/")
        return {}

    os.makedirs(output_dir, exist_ok=True)
    results_path = os.path.join(output_dir, "results.json")

    official_module_layout = (
        eval_script.parent.name == "answer_evaluation"
        and eval_script.parent.parent.name == "scripts"
        and eval_script.parent.parent.parent.name == "src"
    )
    entrypoint = (
        [sys.executable, "-m", "src.scripts.answer_evaluation.metrics_based_eval"]
        if official_module_layout else [sys.executable, str(eval_script)]
    )
    cmd = entrypoint + [
        "--questions-file", questions_file,
        "--answers-file", answers_file,
        "--results-file", results_path,
        "--parallelism", str(parallelism),
    ]
    if no_correction:
        cmd.append("--no-correction")
    if resume:
        cmd.append("--resume")

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        cwd=str(eval_script.parent.parent.parent.parent)
        if official_module_layout else None,
    )

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)

    if result.returncode != 0:
        print(f"[WARNING] Evaluation script exited with code {result.returncode}")
        return {}

    if os.path.exists(results_path):
        with open(results_path, encoding="utf-8") as f:
            return json.load(f)

    return {}


def _find_eval_script() -> Path | None:
    """Find the official metrics_based_eval.py script."""
    candidates = [
        Path("eval/answer_evaluation/metrics_based_eval.py"),
        Path("llm_answer/answer_evaluation/metrics_based_eval.py"),
        Path("EnterpriseRAG-Bench/src/scripts/answer_evaluation/metrics_based_eval.py"),
        Path("../EnterpriseRAG-Bench/src/scripts/answer_evaluation/metrics_based_eval.py"),
    ]
    # Also search relative to project root
    project_root = Path(__file__).resolve().parent.parent
    candidates.insert(0, project_root / "eval" / "answer_evaluation" / "metrics_based_eval.py")
    candidates.insert(1, project_root / "llm_answer" / "answer_evaluation" / "metrics_based_eval.py")

    for p in candidates:
        if p.exists():
            return p
    return None


def compute_simple_metrics(
    answers: list[dict],
    questions: dict[str, dict],
) -> dict:
    """
    Compute simplified metrics without LLM-as-judge.
    Only computes document recall and invalid extra docs.
    Used when the official eval script is not available or for quick checks.
    """
    total = len(answers)
    if total == 0:
        return {"total": 0}

    recall_sum = 0.0
    invalid_sum = 0.0
    recall_count = 0

    per_question = []
    for a in answers:
        qid = a["question_id"]
        q = questions.get(qid, {})
        gold_ids = set(q.get("expected_doc_ids", []))
        ret_ids = a.get("document_ids", [])

        if gold_ids:
            recall = len(set(ret_ids) & gold_ids) / len(gold_ids)
            recall_sum += recall
            recall_count += 1
        else:
            recall = None

        extra = set(ret_ids) - gold_ids if gold_ids else set()
        invalid_sum += len(extra)

        per_question.append({
            "question_id": qid,
            "document_recall_pct": round(recall * 100, 1) if recall is not None else None,
            "invalid_extra_docs": len(extra) if gold_ids else None,
        })

    return {
        "total": total,
        "average_recall_pct": round(recall_sum / recall_count * 100, 1) if recall_count else None,
        "average_invalid_extra_docs": round(invalid_sum / total, 1),
        "questions": per_question,
    }
