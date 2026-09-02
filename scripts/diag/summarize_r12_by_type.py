from collections import defaultdict
import json
from pathlib import Path

path = Path('outputs/r12_direct_bge_conan_retrieval_50_20260828/r12_direct_bge_conan_retrieval_50_20260828.json')
rows = json.loads(path.read_text(encoding='utf-8'))['rows']
groups = defaultdict(list)
for row in rows:
    groups[row['question_type']].append(row)
for qtype, items in groups.items():
    print(qtype, len(items), end=' ')
    for k in (30, 120, 240, 1000):
        b = sum(r['bge_rank'] is not None and r['bge_rank'] <= k for r in items)
        c = sum(r['conan_rank'] is not None and r['conan_rank'] <= k for r in items)
        print(f'K{k}: BGE {b}/{len(items)} Conan {c}/{len(items)}', end='; ')
    print()
