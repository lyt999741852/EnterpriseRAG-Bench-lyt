"""Compare v5.2 vs v5.3 on the 10-question validation set."""
import json

BASE = "outputs/pageindex_targeted10_v53_20260803"
PREV = "outputs/pageindex_balanced50_v52_20260803"
QIDS = ["qst_0050", "qst_0093", "qst_0112", "qst_0116",
        "qst_0184", "qst_0231", "qst_0251", "qst_0154", "qst_0298", "qst_0301"]


def load(path: str) -> dict:
    return {json.loads(l)["question_id"]: json.loads(l)
            for l in open(path, encoding="utf-8")}


def main() -> None:
    base = json.load(open(f"{BASE}/results.json", encoding="utf-8"))
    prev = json.load(open(f"{PREV}/results.json", encoding="utf-8"))
    base_by = {q["question_id"]: q for q in base["questions"]}
    prev_by = {q["question_id"]: q for q in prev["questions"]}
    answers = load(f"{BASE}/answers.jsonl")
    traces = load(f"{BASE}/route_trace.jsonl")

    print(f"{'qid':<9}{'v52':<14}{'v53':<14}docs submitted / trace action")
    for qid in QIDS:
        b = base_by[qid]
        p = prev_by[qid]
        a = answers[qid]
        t = traces[qid]
        bm = "T" if b["answer_correct"] else "F"
        pm = "T" if p["answer_correct"] else "F"
        docs = a.get("document_ids") or []
        print(f"{qid:<9}{bm:<14}{pm:<14}{len(docs)} / {t.get('route_action')}")
        if docs:
            print(f"    docs={docs}")


if __name__ == "__main__":
    main()
