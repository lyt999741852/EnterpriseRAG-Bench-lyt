"""Analyze v5.2 50-question results by question type."""
import json

RESULTS = "outputs/pageindex_balanced50_v52_20260803/results.json"
QUESTIONS = "corpus/all_documents/questions.jsonl"


def main() -> None:
    with open(RESULTS) as f:
        data = json.load(f)
    by_type: dict[str, list] = {}
    for q in data["questions"]:
        by_type.setdefault(q["question_type"], []).append(q)
    print(f"{'type':<26}{'n':<4}{'corr':<8}{'comp':<9}{'recall':<9}{'extra':<7}")
    for qtype, items in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
        n = len(items)
        corr = sum(1 for q in items if q["answer_correct"]) / n * 100
        comps = [q.get("completeness_pct") or 0 for q in items]
        comp = sum(comps) / n
        recs = [q.get("document_recall_pct") for q in items if q.get("document_recall_pct") is not None]
        rec = sum(recs) / len(recs) if recs else float("nan")
        extras = [q.get("invalid_extra_docs") or 0 for q in items if q.get("invalid_extra_docs") is not None]
        extra = sum(extras) / len(extras) if extras else float("nan")
        print(f"{qtype:<26}{n:<4}{corr:<8.1f}{comp:<9.1f}{rec:<9.1f}{extra:<7.2f}")
    print()
    print("== wrong answers ==")
    for q in data["questions"]:
        if not q["answer_correct"]:
            print(f"  {q['question_id']} [{q['question_type']}] comp={q.get('completeness_pct')} rec={q.get('document_recall_pct')} extra={q.get('invalid_extra_docs')}")


if __name__ == "__main__":
    main()
