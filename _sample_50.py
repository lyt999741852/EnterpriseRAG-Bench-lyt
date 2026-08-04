"""Generate a stratified 50-question sample with a fixed seed.

Each question type is allocated proportionally to its share of the full 500
questions. The ten v4-validated representative questions are forced in so the
run is directly comparable with v4/v5.1/v5.2; the remaining slots are drawn
deterministically from the rest of each type's pool.
"""
import json
import random
from collections import defaultdict

QUESTIONS = "questions.jsonl"
SEED = 20260803
TOTAL = 50

# v4 representative questions (validated across v4/v5.1/v5.2)
ANCHOR_QIDS = {
    "qst_0301",  # intra_document_reasoning
    "qst_0341",  # project_related
    "qst_0154",  # basic
    "qst_0298",  # semantic
    "qst_0386",  # constrained
    "qst_0459",  # miscellaneous
    "qst_0498",  # info_not_found
    "qst_0416",  # conflicting_info
    "qst_0432",  # completeness
    "qst_0480",  # high_level
}


def main() -> None:
    by_type: dict[str, list[str]] = defaultdict(list)
    total = 0
    for line in open(QUESTIONS, encoding="utf-8"):
        q = json.loads(line)
        by_type[q["question_type"]].append(q["question_id"])
        total += 1
    print(f"full pool: {total} questions across {len(by_type)} types")
    for t, ids in sorted(by_type.items()):
        print(f"  {t}: {len(ids)}")

    rng = random.Random(SEED)
    selected: list[str] = []
    for qtype, ids in sorted(by_type.items()):
        quota = max(1, round(TOTAL * len(ids) / total))
        pool = [qid for qid in ids if qid not in ANCHOR_QIDS]
        chosen = [qid for qid in ids if qid in ANCHOR_QIDS]
        rng.shuffle(pool)
        chosen.extend(pool[: max(0, quota - len(chosen))])
        selected.extend(chosen)
        print(f"  {qtype}: quota={quota} chosen={len(chosen)}")
    # adjust to exactly TOTAL (drop extras from the largest over-quota type)
    while len(selected) > TOTAL:
        largest = max(by_type, key=lambda t: len(by_type[t]))
        drop = [q for q in selected if q in by_type[largest] and q not in ANCHOR_QIDS]
        if drop:
            selected.remove(drop[-1])
        else:
            selected.pop()
    while len(selected) < TOTAL:
        # add from the type furthest below its quota
        counts = {t: sum(1 for q in selected if q in by_type[t]) for t in by_type}
        lagging = min(by_type, key=lambda t: counts[t] / max(1, len(by_type[t])))
        pool = [q for q in by_type[lagging] if q not in selected]
        selected.append(pool[0])
    selected.sort(key=lambda qid: int(qid.split("_")[1]))
    print(f"\nselected {len(selected)} questions:")
    print(json.dumps(selected, indent=2))


if __name__ == "__main__":
    main()
