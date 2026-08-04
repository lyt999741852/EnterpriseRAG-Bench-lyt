"""
Document indexer: load corpus, chunk, embed, build BM25 + FAISS indices.
Outputs cached index files so re-indexing is only needed when corpus changes.
"""

from __future__ import annotations

import json
import hashlib
import os
import pickle
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from rank_bm25 import BM25Okapi

from .embedder import Embedder, create_embedder, EmbedderConfig


CHUNK_ID_STRATEGY = "dataset-duplicate-path-v2"


# ---------------------------------------------------------------------------
# Chunk dataclass
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    chunk_id: str               # unique per chunk
    doc_id: str                 # parent document dsid
    source_type: str            # data source subdirectory name
    text: str
    char_start: int             # character offset in original doc
    char_end: int


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class IndexerConfig:
    corpus_dir: str = "data/demo_corpus"
    chunk_size: int = 512
    chunk_overlap: int = 0
    embedder: EmbedderConfig = field(default_factory=EmbedderConfig)
    overwrite: bool = False
    enable_faiss: bool = True       # skip FAISS for BM25-only baselines
    enable_bm25: bool = True
    cache_dir: str | None = None
    chunker_version: str = "fixed-v2"
    manifest_enabled: bool = True


# ---------------------------------------------------------------------------
# Simple tokenizer for BM25
# ---------------------------------------------------------------------------

def _simple_tokenize(text: str) -> list[str]:
    """Whitespace + punctuation split, lowercase."""
    return re.findall(r"\w+", text.lower())


# ---------------------------------------------------------------------------
# Indexer
# ---------------------------------------------------------------------------

class Indexer:
    """Build and persist BM25 + FAISS + chunk metadata for the corpus."""

    def __init__(self, config: IndexerConfig):
        self.config = config
        self.corpus_root = Path(config.corpus_dir)
        self.cache_dir = (
            Path(config.cache_dir)
            if config.cache_dir
            else self.corpus_root.parent / ".index_cache"
        )
        self._embedder: Optional[Embedder] = None
        self.failures: list[dict] = []
        self._dataset_signature_cache: dict | None = None

        # Built data
        self.chunks: list[Chunk] = []
        self.doc_ids: set[str] = set()
        self.source_types: set[str] = set()
        self.duplicate_doc_ids: set[str] = set()

    # --- Public API ---

    def build(self) -> dict:
        """Build or load from cache. Returns metadata dict."""
        if not self.corpus_root.exists():
            raise FileNotFoundError(f"Corpus directory not found: {self.corpus_root}")
        if self._cache_valid():
            return self._load()

        t0 = time.time()
        self._load_documents()
        print(f"Loaded {len(self.doc_ids)} docs from {len(self.source_types)} sources "
              f"in {time.time()-t0:.1f}s")

        if self.config.enable_bm25:
            t0 = time.time()
            self._build_bm25()
            print(f"BM25 index built: {self._bm25_chunk_count} chunks in {time.time()-t0:.1f}s")
        else:
            print("BM25 index skipped (enable_bm25=False)")

        if self.config.enable_faiss:
            t0 = time.time()
            self._build_faiss()
            print(f"FAISS index built: {self._faiss_index.ntotal} vectors in {time.time()-t0:.1f}s")
        else:
            print("FAISS index skipped (enable_faiss=False)")

        meta = self._save()
        return meta

    def get_chunk_texts(self) -> list[str]:
        return [c.text for c in self.chunks]

    @property
    def bm25(self) -> BM25Okapi:
        if not hasattr(self, "_bm25"):
            raise RuntimeError("Index not built. Call indexer.build() first.")
        return self._bm25

    @property
    def faiss_index(self):
        if not hasattr(self, "_faiss_index"):
            raise RuntimeError("Index not built. Call indexer.build() first.")
        return self._faiss_index

    @property
    def faiss_id_to_chunk(self) -> dict[int, int]:
        """Maps FAISS internal id -> chunk index in self.chunks."""
        if not hasattr(self, "_faiss_id_to_chunk"):
            raise RuntimeError("Index not built.")
        return self._faiss_id_to_chunk

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = create_embedder(self.config.embedder)
        return self._embedder

    # --- Internal: document loading ---

    def _load_documents(self):
        """Load and checkpoint chunks, isolating individual file failures."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        dataset_signature = self._dataset_signature()
        dataset_duplicate_doc_ids = set(
            dataset_signature.get("duplicate_doc_ids", [])
        )
        self.duplicate_doc_ids = set(dataset_duplicate_doc_ids)
        manifest = self._open_manifest() if self.config.manifest_enabled else None
        preprocess_fingerprint = self._preprocess_fingerprint()
        partial_path = self.cache_dir / "chunks.jsonl.partial"
        final_path = self.cache_dir / "chunks.jsonl"

        completed_paths: set[str] = set()
        checkpoint_path: Path | None = None
        if manifest is not None:
            stored_fingerprint = self._manifest_get(manifest, "preprocess_fingerprint")
            stored_complete = self._manifest_get(manifest, "preprocess_complete") == "1"
            if stored_fingerprint == preprocess_fingerprint:
                checkpoint_path = final_path if stored_complete and final_path.exists() else partial_path
                completed_paths = {
                    row[0] for row in manifest.execute(
                        "SELECT file_path FROM documents WHERE status IN ('chunked', 'skipped')"
                    )
                }
            else:
                manifest.execute("DELETE FROM documents")
                manifest.execute("DELETE FROM metadata")
                manifest.commit()
                if partial_path.exists():
                    partial_path.unlink()
            self._manifest_set(manifest, "preprocess_fingerprint", preprocess_fingerprint)
            self._manifest_set(manifest, "preprocess_complete", "0")
            manifest.commit()

        # Recover already checkpointed chunks. A set of deterministic IDs makes
        # a crash between file append and manifest commit harmless on restart.
        seen_chunk_ids: set[str] = set()
        if checkpoint_path is not None and checkpoint_path.exists():
            with open(checkpoint_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    chunk = Chunk(**json.loads(line))
                    if chunk.chunk_id in seen_chunk_ids:
                        continue
                    seen_chunk_ids.add(chunk.chunk_id)
                    self.chunks.append(chunk)
                    self.doc_ids.add(chunk.doc_id)
                    self.source_types.add(chunk.source_type)
            print(
                f"  Resuming preprocessing: {len(completed_paths)} docs, "
                f"{len(self.chunks)} chunks"
            )

        if (
            checkpoint_path == final_path
            and len(completed_paths) >= self._dataset_signature()["txt_count"]
        ):
            if manifest is not None:
                self._manifest_set(manifest, "preprocess_complete", "1")
                manifest.commit()
                manifest.close()
            return

        write_mode = "a" if checkpoint_path == partial_path and partial_path.exists() else "w"
        # A complete final checkpoint is copied into a new append checkpoint only
        # when unfinished documents remain (normally only previously failed files).
        if checkpoint_path == final_path and completed_paths:
            with open(partial_path, "w", encoding="utf-8") as target:
                for chunk in self.chunks:
                    target.write(self._chunk_json(chunk) + "\n")
            write_mode = "a"

        count = 0
        with open(partial_path, write_mode, encoding="utf-8") as chunk_file:
            for src_dir in sorted(self.corpus_root.iterdir()):
                if not src_dir.is_dir():
                    continue
                source_type = src_dir.name
                self.source_types.add(source_type)
                print(f"  Loading {source_type}...")
                src_count = 0
                for txt_file in sorted(src_dir.rglob("*.txt")):
                    if not txt_file.is_file():
                        continue
                    relative_path = txt_file.relative_to(self.corpus_root).as_posix()
                    if relative_path in completed_paths:
                        src_count += 1
                        count += 1
                        continue

                    doc_id = txt_file.stem.split("__")[0]
                    try:
                        text = txt_file.read_text(encoding="utf-8", errors="replace")
                        stat = txt_file.stat()
                    except OSError as e:
                        failure = {
                            "file_path": relative_path,
                            "doc_id": doc_id,
                            "error": f"{type(e).__name__}: {e}",
                        }
                        self.failures.append(failure)
                        self._manifest_record(
                            manifest, relative_path, doc_id, source_type,
                            "failed", 0, "", failure["error"], None,
                        )
                        continue

                    if not text.strip():
                        self._manifest_record(
                            manifest, relative_path, doc_id, source_type,
                            "skipped", 0, hashlib.sha256(b"").hexdigest(),
                            "empty document", stat,
                        )
                        src_count += 1
                        count += 1
                        continue

                    duplicate_doc_id = doc_id in dataset_duplicate_doc_ids
                    path_tag = hashlib.sha256(
                        relative_path.encode("utf-8")
                    ).hexdigest()[:12]
                    new_chunks: list[Chunk] = []
                    for i, chunk_data in enumerate(self._chunk_text(text)):
                        if duplicate_doc_id:
                            chunk_id = (
                                f"{doc_id}__{self.config.chunker_version}__"
                                f"dup-{path_tag}__chunk{i:05d}"
                            )
                        else:
                            chunk_id = (
                                f"{doc_id}__{self.config.chunker_version}__"
                                f"chunk{i:05d}"
                            )
                        chunk = Chunk(
                            chunk_id=chunk_id,
                            doc_id=doc_id,
                            source_type=source_type,
                            text=chunk_data["text"],
                            char_start=chunk_data["start"],
                            char_end=chunk_data["end"],
                        )
                        if chunk.chunk_id not in seen_chunk_ids:
                            seen_chunk_ids.add(chunk.chunk_id)
                            new_chunks.append(chunk)
                            chunk_file.write(self._chunk_json(chunk) + "\n")

                    self.chunks.extend(new_chunks)
                    self.doc_ids.add(doc_id)
                    self._manifest_record(
                        manifest, relative_path, doc_id, source_type,
                        "chunked", len(new_chunks),
                        hashlib.sha256(text.encode("utf-8")).hexdigest(), "", stat,
                    )
                    src_count += 1
                    count += 1
                    if count % 1000 == 0 and manifest is not None:
                        os.fsync(chunk_file.fileno())
                        manifest.commit()
                    if count % 5000 == 0:
                        print(f"    ... {count} docs loaded, {len(self.chunks)} chunks")
                print(f"    {source_type}: {src_count} docs")

            chunk_file.flush()
            os.fsync(chunk_file.fileno())

        os.replace(partial_path, final_path)
        if manifest is not None:
            self._manifest_set(manifest, "preprocess_complete", "1")
            manifest.commit()
            manifest.close()

    def _chunk_text(self, text: str) -> list[dict]:
        """Fixed-size chunking by whitespace tokens with exact char offsets."""
        tokens = list(re.finditer(r"\S+", text))
        size = self.config.chunk_size
        overlap = self.config.chunk_overlap
        if len(tokens) <= size:
            return [{"text": text, "start": 0, "end": len(text)}]

        chunks = []
        step = size - overlap if overlap < size else 1
        for i in range(0, len(tokens), step):
            end_index = min(i + size, len(tokens))
            start = tokens[i].start()
            end = tokens[end_index - 1].end()
            chunks.append({"text": text[start:end], "start": start, "end": end})
        return chunks

    # --- Internal: BM25 ---

    def _build_bm25(self):
        tokenized = [_simple_tokenize(c.text) for c in self.chunks]
        self._bm25_chunk_count = len(tokenized)
        self._bm25 = BM25Okapi(tokenized)
        # BM25Okapi has already materialized document frequencies and lengths;
        # dropping the temporary token lists materially reduces peak residency.
        del tokenized

    # --- Internal: FAISS ---

    def _build_faiss(self):
        import faiss
        if not self.chunks:
            raise RuntimeError("Cannot build a vector index with zero chunks")
        # Add bounded batches directly to FAISS. This avoids holding a second
        # full text list and a full corpus-sized NumPy matrix in memory.
        batch_size = max(1, int(self.config.embedder.batch_size or 256))
        self._faiss_index = None
        for start in range(0, len(self.chunks), batch_size):
            batch = self.chunks[start:start + batch_size]
            vectors = self.embedder.encode(
                [chunk.text for chunk in batch], show_progress=False
            ).astype(np.float32)
            if self._faiss_index is None:
                self._faiss_index = faiss.IndexFlatIP(vectors.shape[1])
            self._faiss_index.add(vectors)
            if (start // batch_size + 1) % 20 == 0 or start + batch_size >= len(self.chunks):
                print(f"  Embedding: {min(start + batch_size, len(self.chunks))}/{len(self.chunks)}")
        self._faiss_id_to_chunk = {i: i for i in range(len(self.chunks))}

    # --- Internal: cache ---

    @staticmethod
    def _chunk_json(chunk: Chunk) -> str:
        return json.dumps({
            "chunk_id": chunk.chunk_id,
            "doc_id": chunk.doc_id,
            "source_type": chunk.source_type,
            "text": chunk.text,
            "char_start": chunk.char_start,
            "char_end": chunk.char_end,
        }, ensure_ascii=False)

    def _dataset_signature(self) -> dict:
        """Build a stable, metadata-only corpus signature without reading content."""
        if self._dataset_signature_cache is not None:
            return self._dataset_signature_cache
        count = 0
        total_size = 0
        max_mtime_ns = 0
        stat_failures = 0
        doc_id_counts: dict[str, int] = {}
        sources = []
        for src_dir in sorted(self.corpus_root.iterdir()):
            if not src_dir.is_dir():
                continue
            sources.append(src_dir.name)
            for txt_file in src_dir.rglob("*.txt"):
                try:
                    stat = txt_file.stat()
                except OSError:
                    stat_failures += 1
                    continue
                count += 1
                total_size += stat.st_size
                max_mtime_ns = max(max_mtime_ns, stat.st_mtime_ns)
                doc_id = txt_file.stem.split("__")[0]
                doc_id_counts[doc_id] = doc_id_counts.get(doc_id, 0) + 1
        duplicate_doc_ids = sorted(
            doc_id for doc_id, occurrences in doc_id_counts.items()
            if occurrences > 1
        )
        self._dataset_signature_cache = {
            "root": str(self.corpus_root.resolve()),
            "sources": sources,
            "txt_count": count,
            "total_size": total_size,
            "max_mtime_ns": max_mtime_ns,
            "stat_failures": stat_failures,
            "duplicate_doc_ids": duplicate_doc_ids,
        }
        return self._dataset_signature_cache

    @staticmethod
    def _hash_payload(payload: dict) -> str:
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _preprocess_fingerprint(self) -> str:
        return self._hash_payload({
            "dataset": self._dataset_signature(),
            "chunker_version": self.config.chunker_version,
            "chunk_id_strategy": CHUNK_ID_STRATEGY,
            "chunk_size": self.config.chunk_size,
            "chunk_overlap": self.config.chunk_overlap,
        })

    def _index_fingerprint(self) -> str:
        payload = {
            "preprocess_fingerprint": self._preprocess_fingerprint(),
            "bm25_tokenizer": "simple-word-v1",
            "enable_bm25": self.config.enable_bm25,
            "enable_faiss": self.config.enable_faiss,
        }
        if self.config.enable_faiss:
            payload["embedding"] = {
                "provider": self.config.embedder.provider,
                "model_name": self.config.embedder.model_name,
                "revision": self.config.embedder.revision,
                "dimension": self.config.embedder.dimension,
            }
        return self._hash_payload(payload)

    def _open_manifest(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.cache_dir / "manifest.sqlite3")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                file_path TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                file_size INTEGER,
                mtime_ns INTEGER,
                content_hash TEXT,
                status TEXT NOT NULL,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT NOT NULL DEFAULT ''
            )
            """
        )
        return connection

    @staticmethod
    def _manifest_get(connection: sqlite3.Connection, key: str) -> str | None:
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    @staticmethod
    def _manifest_set(connection: sqlite3.Connection, key: str, value: str):
        connection.execute(
            """
            INSERT INTO metadata(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )

    @staticmethod
    def _manifest_record(
        connection: sqlite3.Connection | None,
        file_path: str,
        doc_id: str,
        source_type: str,
        status: str,
        chunk_count: int,
        content_hash: str,
        error_message: str,
        stat,
    ):
        if connection is None:
            return
        connection.execute(
            """
            INSERT INTO documents(
                file_path, doc_id, source_type, file_size, mtime_ns,
                content_hash, status, chunk_count, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                doc_id = excluded.doc_id,
                source_type = excluded.source_type,
                file_size = excluded.file_size,
                mtime_ns = excluded.mtime_ns,
                content_hash = excluded.content_hash,
                status = excluded.status,
                chunk_count = excluded.chunk_count,
                error_message = excluded.error_message
            """,
            (
                file_path, doc_id, source_type,
                stat.st_size if stat is not None else None,
                stat.st_mtime_ns if stat is not None else None,
                content_hash, status, chunk_count, error_message,
            ),
        )

    def _cache_valid(self) -> bool:
        if self.config.overwrite:
            return False
        meta_path = self.cache_dir / "_meta.json"
        required = [self.cache_dir / "chunks.jsonl"]
        if self.config.enable_bm25:
            required.append(self.cache_dir / "bm25.pkl")
        if self.config.enable_faiss:
            required.append(self.cache_dir / "faiss.index")
        if not meta_path.exists() or any(not path.exists() for path in required):
            return False
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError):
            return False
        return meta.get("index_fingerprint") == self._index_fingerprint()

    def _save(self) -> dict:
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Chunks are already atomically checkpointed by _load_documents().
        chunks_path = self.cache_dir / "chunks.jsonl"
        if not chunks_path.exists():
            temp_chunks = self.cache_dir / "chunks.jsonl.tmp"
            with open(temp_chunks, "w", encoding="utf-8") as f:
                for chunk in self.chunks:
                    f.write(self._chunk_json(chunk) + "\n")
            os.replace(temp_chunks, chunks_path)

        # Save BM25
        if hasattr(self, "_bm25"):
            with open(self.cache_dir / "bm25.pkl", "wb") as f:
                pickle.dump(self._bm25, f)

        # Save FAISS (optional)
        if hasattr(self, "_faiss_index"):
            import faiss
            faiss.write_index(self._faiss_index, str(self.cache_dir / "faiss.index"))

        meta = {
            "schema_version": 2,
            "index_fingerprint": self._index_fingerprint(),
            "dataset_signature": self._dataset_signature(),
            "num_docs": len(self.doc_ids),
            "num_chunks": len(self.chunks),
            "source_types": sorted(self.source_types),
            "failed_files": len(self.failures),
            "duplicate_doc_ids": len(self.duplicate_doc_ids),
        }
        meta_temp = self.cache_dir / "_meta.json.tmp"
        with open(meta_temp, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        os.replace(meta_temp, self.cache_dir / "_meta.json")

        failures_temp = self.cache_dir / "failed_files.jsonl.tmp"
        with open(failures_temp, "w", encoding="utf-8") as f:
            for failure in self.failures:
                f.write(json.dumps(failure, ensure_ascii=False) + "\n")
        os.replace(failures_temp, self.cache_dir / "failed_files.jsonl")

        print(f"Index cache saved to {self.cache_dir}")
        return meta

    def _load(self) -> dict:
        print(f"Loading index from cache: {self.cache_dir}")

        # Load chunks
        self.chunks = []
        with open(self.cache_dir / "chunks.jsonl", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                self.chunks.append(Chunk(**d))

        # Load BM25
        bm25_path = self.cache_dir / "bm25.pkl"
        if bm25_path.exists() and self.config.enable_bm25:
            with open(bm25_path, "rb") as f:
                self._bm25 = pickle.load(f)

        # Load FAISS (optional)
        faiss_path = self.cache_dir / "faiss.index"
        if faiss_path.exists():
            import faiss
            self._faiss_index = faiss.read_index(str(faiss_path))
            self._faiss_id_to_chunk = {i: i for i in range(len(self.chunks))}

        # Load meta
        with open(self.cache_dir / "_meta.json", encoding="utf-8") as f:
            meta = json.load(f)

        self.doc_ids = {chunk.doc_id for chunk in self.chunks}
        self.source_types = {chunk.source_type for chunk in self.chunks}

        print(f"Loaded {meta['num_chunks']} chunks from {meta['num_docs']} docs")
        return meta
