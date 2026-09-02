"""Local sanity test for hierarchical-v1 chunker (approx tokenizer)."""
import re
import sys

sys.path.insert(0, r"d:\EnterpriseRAG-Bench")

import src.indexer as indexer

# monkeypatch token counting with whitespace approximation
indexer._count_tokens = lambda t: max(1, len(t.split()))


def check(text, size=384, overlap=64):
    chunks = indexer._chunk_text_hierarchical(text, size, overlap)
    total_tokens = sum(indexer._count_tokens(c["text"]) for c in chunks)
    print(f"chunks={len(chunks)} total_approx_tokens={total_tokens}")
    ok = True
    for i, c in enumerate(chunks):
        t = indexer._count_tokens(c["text"])
        # chunk may carry overlap tail: hard cap = size + overlap (must stay < 512 API limit)
        over = t > size + overlap
        bad_offset = not (0 <= c["start"] <= c["end"] <= len(text))
        if over or bad_offset:
            ok = False
        overlap_ok = True
        if i > 0:
            prev = chunks[i - 1]
            # overlap should share some tail tokens of prev
            shared = len(set(prev["text"].split()) & set(c["text"].split()))
            if shared == 0:
                overlap_ok = False
        print(f"  chunk{i}: tokens={t} start={c['start']} end={c['end']} over={over} bad_off={bad_offset} shared_with_prev={'-' if i==0 else 'yes' if overlap_ok else 'NO'}")
        if over or bad_offset or (i > 0 and not overlap_ok):
            ok = False
    return ok, chunks


# 1. short doc -> single chunk
doc1 = "This is a short document. " * 20  # 160 tokens
ok1, _ = check(doc1)

# 2. long doc with paragraphs
doc2 = "\n\n".join(
    f"Paragraph number {i} contains some sentences about enterprise topics and infrastructure details. " * 6
    for i in range(30)
)  # 30 paragraphs x ~80 tokens
ok2, _ = check(doc2)

# 3. doc with markdown headings
doc3 = "# Section One\n\n" + "Text body line. " * 100 + "\n\n## Section Two\n\n" + "More content here. " * 300
ok3, _ = check(doc3)

# 4. doc with a huge single paragraph (> size)
doc4 = "Sentence one about things. " * 200  # 800 tokens single paragraph
ok4, _ = check(doc4)

# 5. email-like doc with header lines ending in ':'
doc5 = "From: Alice <alice@corp.com>\nTo: Bob\nSubject: Weekly report\nDate: 2026-08-04\n\n" + "Body content with details. " * 120
ok5, _ = check(doc5)

print("\nALL OK" if all([ok1, ok2, ok3, ok4, ok5]) else "SOME FAILED")
