from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
ids = [str(json.loads(line)["question_id"]) for line in (ROOT / "questions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
if len(ids) != 500 or len(set(ids)) != 500:
    raise SystemExit(f"expected 500 unique question IDs, got {len(ids)}")
(ROOT / "configs/s3_full500_question_ids_20260902.txt").write_text("\n".join(ids) + "\n", encoding="utf-8")
print(f"wrote {len(ids)} IDs")
