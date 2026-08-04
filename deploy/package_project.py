"""Check project sizes and create a zip archive excluding large data directories."""
import os
import zipfile
import time

ROOT = r"d:\EnterpriseRAG-Bench"
OUTPUT_ZIP = r"d:\EnterpriseRAG-Bench_TRANSFER.zip"

# Directories to EXCLUDE (large data, can be re-downloaded or rebuilt)
EXCLUDE_DIRS = {
    ".git",
    "corpus",           # 2.5GB raw documents - on server at /opt/enterprise-rag-bench/app/corpus
    "confluence",       # part of corpus data
    "demo_corpus",      # demo data, not needed
    "slice_inspect",    # inspection data, not needed
    ".index_cache",     # cached indexes, can be rebuilt
    "__pycache__",      # python cache
    ".agents",          # IDE agent data
    ".codex",           # IDE codex data
    ".workbuddy",       # IDE workbuddy data
}

# Files to EXCLUDE
EXCLUDE_FILES = {
    "github_slice_0001.zip",
    "github_slice_0002.zip",
}

print("=" * 60)
print("EnterpriseRAG-Bench Project Packager")
print("=" * 60)

# Phase 1: Scan and report
print("\n[1/3] Scanning project files...")
file_count = 0
total_size = 0
skipped_count = 0
skipped_size = 0
file_list = []

for dirpath, dirnames, filenames in os.walk(ROOT):
    # Filter out excluded directories
    dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]

    for filename in filenames:
        filepath = os.path.join(dirpath, filename)
        relpath = os.path.relpath(filepath, ROOT)

        if filename in EXCLUDE_FILES:
            skipped_count += 1
            try:
                skipped_size += os.path.getsize(filepath)
            except OSError:
                pass
            continue

        try:
            fsize = os.path.getsize(filepath)
        except OSError:
            continue

        file_list.append((filepath, relpath, fsize))
        file_count += 1
        total_size += fsize

print(f"  Files to include: {file_count}")
print(f"  Total size: {total_size / 1e6:.1f} MB")
print(f"  Files skipped: {skipped_count}")
print(f"  Skipped size: {skipped_size / 1e6:.1f} MB")

# Show top-level breakdown
print("\n  Top-level breakdown:")
dir_sizes = {}
for filepath, relpath, fsize in file_list:
    top = relpath.split(os.sep)[0]
    dir_sizes[top] = dir_sizes.get(top, 0) + fsize
for name, size in sorted(dir_sizes.items(), key=lambda x: -x[1])[:15]:
    print(f"    {size/1e6:8.2f} MB  {name}/")

# Phase 2: Create ZIP
print(f"\n[2/3] Creating archive: {OUTPUT_ZIP}")
start = time.time()
with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
    for filepath, relpath, fsize in file_list:
        zf.write(filepath, relpath)

elapsed = time.time() - start
zip_size = os.path.getsize(OUTPUT_ZIP)
print(f"  Done in {elapsed:.1f}s")
print(f"  Archive size: {zip_size / 1e6:.1f} MB")
print(f"  Compression ratio: {zip_size/total_size*100:.1f}%")

# Phase 3: Summary
print(f"\n[3/3] Summary")
print(f"  Archive: {OUTPUT_ZIP}")
print(f"  Size:    {zip_size / 1e6:.1f} MB")
print(f"  Files:   {file_count}")
print()
print("  Excluded (can be re-obtained):")
print("    - corpus/          (2.5GB raw docs, on server)")
print("    - confluence/      (corpus subset)")
print("    - demo_corpus/     (demo data)")
print("    - slice_inspect/   (inspection data)")
print("    - .index_cache/    (rebuildable)")
print("    - .git/            (version control)")
print("    - github_slice_*.zip (raw data zips)")
print()
print("  To extract: right-click -> Extract All, or:")
print("    python -c \"import zipfile; zipfile.ZipFile(r'path.zip').extractall(r'dest')\"")
