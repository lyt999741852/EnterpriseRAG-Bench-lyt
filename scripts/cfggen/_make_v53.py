"""Create v5.3 validation config: 7 retrieval-miss questions + 3 anchors,
with query_rewrite enabled for basic/semantic."""
import re

SRC = "configs/eval_pageindex_balanced50_v52.yaml"
DST = "configs/eval_pageindex_targeted10_v53.yaml"
QIDS = [
    "qst_0050", "qst_0093", "qst_0112", "qst_0116",   # basic retrieval misses
    "qst_0184", "qst_0231", "qst_0251",               # semantic retrieval misses
    "qst_0154", "qst_0298", "qst_0301",               # anchors (no regression)
]


def main() -> None:
    src = open(SRC, encoding="utf-8").read()
    block = "  question_ids:\n" + "".join(f'    - "{q}"\n' for q in QIDS)
    src = re.sub(r"  question_ids:\n(?:    - .*\n)+", block, src)
    src = src.replace("balanced50_v52", "targeted10_v53")
    src = src.replace(
        "v5.2 balanced 50-question stratified run (fixed seed 20260803)",
        "v5.3 query-rewrite validation: 7 retrieval-miss + 3 anchors",
    )
    # enable query rewriting for basic/semantic after the retrieval block
    marker = "  method: \"hybrid\""
    add = (
        "\n  query_rewrite:\n"
        "    enabled: true\n"
        "    types: [\"basic\", \"semantic\"]\n"
        "    max_queries: 2\n"
    )
    assert marker in src
    src = src.replace(marker, marker + add, 1)
    with open(DST, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"created {DST}")


if __name__ == "__main__":
    main()
