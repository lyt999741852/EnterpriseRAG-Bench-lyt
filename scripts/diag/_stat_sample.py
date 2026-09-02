"""Length distribution of real v2 chunks (server sample, 2048 rows)."""
import json
import statistics

PATH = r"d:\EnterpriseRAG-Bench\scripts\diag\_sample_v2_chunks.jsonl"

lens = []
with open(PATH, encoding="utf-8") as f:
    for i, line in enumerate(f):
        if i >= 2048:
            break
        lens.append(len(json.loads(line).get("text", "")))

lens.sort()
n = len(lens)
print(f"n={n}")
print(f"max={max(lens)} mean={statistics.mean(lens):.0f} "
      f"p50={lens[n // 2]} p75={lens[int(n * 0.75)]} "
      f"p90={lens[int(n * 0.90)]} p95={lens[int(n * 0.95)]} p99={lens[int(n * 0.99)]}")
for threshold in (800, 1000, 1200, 1500, 2000):
    count = sum(1 for x in lens if x > threshold)
    print(f"chars>{threshold}: {count} ({100 * count / n:.1f}%)")
