"""Create the 50-question stratified config from the 10-question template."""
import json
import re
import subprocess

SRC = "configs/eval_pageindex_balanced10_v52.yaml"
DST = "configs/eval_pageindex_balanced50_v52.yaml"


def main() -> None:
    out = subprocess.run(
        ["python", "_sample_50.py"], capture_output=True, text=True, encoding="utf-8"
    )
    start = out.stdout.find("[")
    end = out.stdout.rfind("]") + 1
    qids = json.loads(out.stdout[start:end])
    print("qids:", len(qids))

    src = open(SRC, encoding="utf-8").read()
    block = "  question_ids:\n" + "".join(f'    - "{q}"\n' for q in qids)
    src = re.sub(r"  question_ids:\n(?:    - .*\n)+", block, src)
    src = src.replace("balanced10_v52", "balanced50_v52")
    src = src.replace(
        "v5.2 balanced 10-question run (v4 question set)",
        "v5.2 balanced 50-question stratified run (fixed seed 20260803)",
    )
    with open(DST, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"created {DST}")


if __name__ == "__main__":
    main()
