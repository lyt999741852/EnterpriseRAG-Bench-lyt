"""Elasticsearch vector indexing and retrieval for EnterpriseRAG-Bench."""

from __future__ import annotations

import base64
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np

from .embedder import Embedder
from .indexer import Chunk
from .retriever import RetrieveResult


@dataclass
class ElasticsearchConfig:
    url: str = "http://127.0.0.1:9200"
    index_name: str = "enterprise-rag-bge-small-v1"
    alias_name: str = "enterprise-rag-bge-small"
    bulk_size: int = 256
    request_timeout: int = 180
    username_env: str = ""
    password_env: str = ""
    shards: int = 1
    # knn (ES 8.x native) | script_score (ES 7.x compatible cosineSimilarity)
    dense_mode: str = "knn"
    # Parallel embedding API requests during indexing (1 = serial).
    embedding_concurrency: int = 1
    # Number of chunks assigned to one concurrent worker group. This is not
    # the API request batch size: the Conan endpoint limits total input
    # context tokens (512), so a group may fall back to smaller requests.
    embedding_group_size: int = 32
    # Conan's total-token window makes one text per request the safe setting.
    embedding_request_batch_size: int = 1


class ElasticsearchBackend:
    """Small dependency-free ES client with resumable, idempotent bulk indexing."""

    def __init__(self, config: ElasticsearchConfig):
        self.config = config
        self.base_url = config.url.rstrip("/")

    def health(self) -> dict:
        return self._request("GET", "/_cluster/health")

    def ensure_index(self, dimension: int) -> None:
        if dimension <= 0:
            raise ValueError("Embedding dimension must be positive")
        exists = self._request(
            "HEAD", f"/{self.config.index_name}", allowed_statuses={404}
        )
        if exists is None:
            self._request(
                "PUT",
                f"/{self.config.index_name}",
                self._index_definition(dimension),
            )
        else:
            mapping = self._request("GET", f"/{self.config.index_name}/_mapping")
            properties = mapping[self.config.index_name]["mappings"]["properties"]
            actual_dimension = properties.get("embedding", {}).get("dims")
            if actual_dimension != dimension:
                raise RuntimeError(
                    f"ES index dimension is {actual_dimension}, embedder returned "
                    f"{dimension}; use a new versioned index"
                )
            # Add fields introduced after an index was first provisioned.
            self._request(
                "PUT",
                f"/{self.config.index_name}/_mapping",
                {"properties": self._metadata_properties()},
            )

        aliases = self._request(
            "GET", f"/{self.config.index_name}/_alias", allowed_statuses={404}
        )
        if aliases is None or self.config.alias_name not in (
            aliases.get(self.config.index_name, {}).get("aliases", {})
        ):
            self._request("POST", "/_aliases", {"actions": [{
                "add": {
                    "index": self.config.index_name,
                    "alias": self.config.alias_name,
                }
            }]})

    def _encode_batch_with_split(
        self, embedder: Embedder, chunks: list[Chunk]
    ) -> tuple[list[Chunk], np.ndarray]:
        """Encode chunk texts with API length-limit tolerance and concurrency.

        Chunks are split into groups of at most 512 (the embedding API batch
        cap) and encoded concurrently via a thread pool (API is stateless, so
        parallel requests are safe). Groups are processed in order, so the
        returned pieces/vectors keep chunk-count parity and ordering.
        """
        if not chunks:
            return [], np.zeros((0, embedder.dimension), dtype=np.float32)
        # Keep enough independent groups in flight for concurrency. The
        # embedding endpoint's 512-token limit applies to the whole request,
        # not to the number of input strings, so bulk_size=512 cannot be used
        # as the concurrency work-unit size for 448-token chunks.
        group_size = max(1, int(self.config.embedding_group_size))
        concurrency = max(1, int(self.config.embedding_concurrency))
        groups = [
            chunks[i:i + group_size] for i in range(0, len(chunks), group_size)
        ]
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            results = list(pool.map(partial(self._encode_group, embedder), groups))
        pieces = [piece for group_pieces, _ in results for piece in group_pieces]
        matrices = [vectors for _, vectors in results]
        if not pieces or not matrices:
            raise RuntimeError("Embedding produced no vectors for a non-empty batch")
        return pieces, np.vstack(matrices).astype(np.float32)

    def _encode_group(
        self, embedder: Embedder, chunks: list[Chunk]
    ) -> tuple[list[Chunk], np.ndarray]:
        """Encode one group with bisect/split fallback for oversized texts.

        The embedding API caps inputs at 512 tokens (its own tokenizer), which
        can differ from the chunker's tokenizer for token-dense text. When a
        batch fails with 400, items are bisected until every piece encodes;
        split pieces are emitted as extra vectors in order, so the caller must
        keep chunk-count parity with the returned matrix.
        """
        pieces: list[Chunk] = []
        encoded: list[np.ndarray] = []
        pending: list[Chunk] = list(chunks)
        attempts = 0
        batch_limit = max(1, int(self.config.embedding_request_batch_size))
        while pending and attempts < 200000:
            attempts += 1
            batch = pending[:batch_limit]
            try:
                vecs = embedder.encode(
                    [c.text for c in batch], show_progress=False
                ).astype(np.float32)
                if vecs.ndim != 2 or vecs.shape[0] != len(batch):
                    raise RuntimeError(
                        "Embedding API returned an incomplete batch: "
                        f"shape={vecs.shape}, expected rows={len(batch)}"
                    )
                pieces.extend(batch)
                encoded.append(vecs)
                pending = pending[len(batch):]
                batch_limit = max(1, int(self.config.embedding_request_batch_size))
            except RuntimeError as exc:
                message = str(exc)
                if "400" not in message and "context length" not in message:
                    raise
                if len(batch) == 1:
                    item = batch[0]
                    # Never silently drop a chunk: split it or fail explicitly.
                    if len(item.text) < 80:
                        raise RuntimeError(
                            f"Embedding rejected an unsplittable chunk: {item.chunk_id}"
                        ) from exc
                    # Split the oversized text near its middle (whitespace
                    # boundary), keep both halves as new pseudo-chunks.
                    text = item.text
                    mid = len(text) // 2
                    lo = text.rfind(" ", 0, mid)
                    hi = text.find(" ", mid)
                    cut = lo if lo > 0 and (hi < 0 or mid - lo <= hi - mid) else hi
                    if cut <= 0 or cut >= len(text) - 1:
                        cut = mid
                    left = item.text[:cut].strip()
                    right = item.text[cut:].strip()
                    new_pieces = []
                    if left:
                        new_pieces.append(Chunk(
                            chunk_id=f"{item.chunk_id}__p{len(new_pieces)}",
                            doc_id=item.doc_id,
                            source_type=item.source_type,
                            text=left,
                            char_start=item.char_start,
                            char_end=item.char_start + len(left),
                        ))
                    if right:
                        new_pieces.append(Chunk(
                            chunk_id=f"{item.chunk_id}__p{len(new_pieces)}",
                            doc_id=item.doc_id,
                            source_type=item.source_type,
                            text=right,
                            char_start=item.char_start + len(left),
                            char_end=item.char_end,
                        ))
                    if new_pieces:
                        pending = new_pieces + pending[1:]
                    else:
                        raise RuntimeError(
                            f"Embedding rejected an unsplittable chunk: {item.chunk_id}"
                        ) from exc
                else:
                    # Retry the same batch from its first item, but truly one
                    # at a time; the previous code kept the 32-item window and
                    # could resend the identical failing request forever.
                    pending = batch + pending[len(batch):]
                    batch_limit = 1
        if pending:
            raise RuntimeError(
                f"Embedding batch retry limit exceeded with {len(pending)} chunks pending"
            )
        if not pieces or not encoded:
            raise RuntimeError("Embedding produced no vectors for a non-empty batch")
        return pieces, np.vstack(encoded).astype(np.float32)

    def index_chunks(
        self,
        chunks: list[Chunk],
        embedder: Embedder,
        max_chunks: int | None = None,
        progress_path: str | None = None,
    ) -> dict:
        """Index missing chunks only; deterministic IDs make retries idempotent."""
        self.ensure_index(embedder.dimension)
        limit = len(chunks) if max_chunks is None else min(len(chunks), max_chunks)
        bulk_size = max(1, int(self.config.bulk_size))
        resume_offset = 0
        if progress_path and os.path.exists(progress_path):
            try:
                with open(progress_path, encoding="utf-8") as handle:
                    saved = json.load(handle)
                if int(saved.get("total", limit)) == limit:
                    resume_offset = int(saved.get(
                        "next_chunk_offset", saved.get("examined", 0)
                    ))
                    resume_offset = max(0, min(resume_offset, limit))
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                # A missing/corrupt progress file is safe: deterministic IDs
                # and _mget still make a restart idempotent.
                resume_offset = 0

        examined = resume_offset
        existing = indexed = created = updated = failed = 0
        next_chunk_offset = resume_offset
        started = time.time()

        for start in range(resume_offset, limit, bulk_size):
            batch = chunks[start:min(start + bulk_size, limit)]
            examined += len(batch)
            present = self._existing_ids([chunk.chunk_id for chunk in batch])
            missing = [chunk for chunk in batch if chunk.chunk_id not in present]
            existing += len(batch) - len(missing)
            if not missing:
                self._print_progress(
                    examined, limit, indexed, created, updated, existing, started
                )
                self._write_progress(
                    progress_path, examined, indexed, created, updated,
                    existing, failed, limit,
                    resume_offset=resume_offset,
                    next_chunk_offset=examined,
                )
                next_chunk_offset = examined
                continue

            pieces, vectors = self._encode_batch_with_split(embedder, missing)
            if vectors.shape != (len(pieces), embedder.dimension):
                raise RuntimeError(
                    f"Unexpected embedding shape {vectors.shape}; expected "
                    f"({len(pieces)}, {embedder.dimension})"
                )
            if not np.isfinite(vectors).all():
                raise RuntimeError("Embedding output contains NaN or infinity")

            operations: list[str] = []
            for chunk, vector in zip(pieces, vectors):
                operations.append(json.dumps({"index": {
                    "_index": self.config.index_name,
                    "_id": chunk.chunk_id,
                }}, separators=(",", ":")))
                operations.append(json.dumps({
                    "chunk_id": chunk.chunk_id,
                    "doc_id": chunk.doc_id,
                    "source_type": chunk.source_type,
                    "text": chunk.text,
                    "chunk_index": self._chunk_index(chunk.chunk_id),
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                    "embedding_model": embedder.config.model_name,
                    "embedding": vector.tolist(),
                }, ensure_ascii=False, separators=(",", ":")))
            response = self._request(
                "POST",
                "/_bulk",
                "\n".join(operations) + "\n",
                content_type="application/x-ndjson",
            )
            for item in response.get("items", []):
                detail = item.get("index", {})
                status = int(detail.get("status", 500))
                if 200 <= status < 300:
                    indexed += 1
                    result = detail.get("result")
                    if result == "created" or status == 201:
                        created += 1
                    elif result == "updated" or status == 200:
                        updated += 1
                else:
                    failed += 1
            if response.get("errors") or failed:
                self._write_progress(
                    progress_path, examined, indexed, created, updated,
                    existing, failed, limit,
                    resume_offset=resume_offset,
                    next_chunk_offset=next_chunk_offset,
                )
                errors = [
                    item.get("index", {}) for item in response.get("items", [])
                    if int(item.get("index", {}).get("status", 500)) >= 300
                ][:5]
                raise RuntimeError(f"Elasticsearch bulk indexing failed: {errors}")
            self._print_progress(
                examined, limit, indexed, created, updated, existing, started
            )
            self._write_progress(
                progress_path, examined, indexed, created, updated,
                existing, failed, limit,
                resume_offset=resume_offset,
                next_chunk_offset=examined,
            )
            next_chunk_offset = examined

        self._request("POST", f"/{self.config.index_name}/_refresh")
        duration = time.time() - started
        return {
            "examined": examined,
            "indexed": indexed,
            "successful": indexed,
            "created": created,
            "updated": updated,
            "existing": existing,
            "failed": failed,
            "duration_seconds": round(duration, 3),
            "chunks_per_second": round(indexed / duration, 2) if duration else 0,
            "created_per_second": round(created / duration, 2) if duration else 0,
            "resume_offset": resume_offset,
            "next_chunk_offset": next_chunk_offset,
            "remaining_chunks": max(0, limit - next_chunk_offset),
            "index": self.config.index_name,
        }

    @staticmethod
    def _write_progress(
        path: str | None,
        examined: int,
        indexed: int,
        created: int,
        updated: int,
        existing: int,
        failed: int,
        total: int,
        *,
        resume_offset: int = 0,
        next_chunk_offset: int | None = None,
    ) -> None:
        """Persist an atomic per-batch checkpoint for restart/audit visibility."""
        if not path:
            return
        if next_chunk_offset is None:
            next_chunk_offset = examined
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        payload = {
            "examined": examined,
            "indexed": indexed,
            "successful": indexed,
            "created": created,
            "updated": updated,
            "existing": existing,
            "failed": failed,
            "total": total,
            "resume_offset": resume_offset,
            "next_chunk_offset": next_chunk_offset,
            "remaining_chunks": max(0, total - next_chunk_offset),
            "progress_percent": round(next_chunk_offset / total * 100, 4)
            if total else 100.0,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        temp_path = f"{path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)

    def count(self) -> int:
        response = self._request("GET", f"/{self.config.index_name}/_count")
        return int(response["count"])

    def bm25_search(self, query: str, size: int) -> list[dict]:
        response = self._request("POST", f"/{self.config.alias_name}/_search", {
            "size": size,
            "_source": [
                "chunk_id", "doc_id", "source_type", "text", "chunk_index"
            ],
            "query": {"match": {"text": {"query": query}}},
        })
        return response.get("hits", {}).get("hits", [])

    def dense_search(self, vector: np.ndarray, size: int) -> list[dict]:
        query_vector = vector.astype(float).tolist()
        if self.config.dense_mode == "script_score":
            # ES 7.x compatible: match_all + cosineSimilarity (needs +1.0 to
            # keep scores non-negative; sort is by score desc by default).
            payload = {
                "size": size,
                "_source": [
                    "chunk_id", "doc_id", "source_type", "text", "chunk_index"
                ],
                "query": {"script_score": {
                    "query": {"match_all": {}},
                    "script": {
                        "source": "cosineSimilarity(params.qv, 'embedding') + 1.0",
                        "params": {"qv": query_vector},
                    },
                }},
            }
        else:
            payload = {
                "size": size,
                "_source": [
                    "chunk_id", "doc_id", "source_type", "text", "chunk_index"
                ],
                "knn": {
                    "field": "embedding",
                    "query_vector": query_vector,
                    "k": size,
                    "num_candidates": max(size, min(10_000, size * 10)),
                },
            }
        response = self._request("POST", f"/{self.config.alias_name}/_search", payload)
        return response.get("hits", {}).get("hits", [])

    def _existing_ids(self, ids: list[str]) -> set[str]:
        response = self._request(
            "POST", f"/{self.config.index_name}/_mget?_source=false", {"ids": ids}
        )
        return {doc["_id"] for doc in response.get("docs", []) if doc.get("found")}

    def _request(
        self,
        method: str,
        path: str,
        payload=None,
        *,
        content_type: str = "application/json",
        allowed_statuses: set[int] | None = None,
    ):
        data = None
        if payload is not None:
            data = (
                payload.encode("utf-8")
                if isinstance(payload, str)
                else json.dumps(payload).encode("utf-8")
            )
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = content_type
        username = os.environ.get(self.config.username_env, "") if self.config.username_env else ""
        password = os.environ.get(self.config.password_env, "") if self.config.password_env else ""
        if username:
            token = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {token}"
        request = Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.config.request_timeout) as response:
                raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
        except HTTPError as error:
            if allowed_statuses and error.code in allowed_statuses:
                return None
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Elasticsearch HTTP {error.code} for {path}: {detail}") from error
        except URLError as error:
            raise RuntimeError(f"Cannot connect to Elasticsearch at {self.base_url}") from error

    def _index_definition(self, dimension: int) -> dict:
        properties = self._metadata_properties()
        properties["embedding"] = {
            "type": "dense_vector",
            "dims": dimension,
            "index": True,
            "similarity": "cosine",
        }
        return {
            "aliases": {self.config.alias_name: {}},
            "settings": {
                "number_of_shards": self.config.shards,
                "number_of_replicas": 0,
                "refresh_interval": "30s",
            },
            "mappings": {"dynamic": "strict", "properties": properties},
        }

    @staticmethod
    def _metadata_properties() -> dict:
        return {
            "chunk_id": {"type": "keyword"},
            "doc_id": {"type": "keyword"},
            "source_type": {"type": "keyword"},
            "text": {"type": "text"},
            "chunk_index": {"type": "integer"},
            "char_start": {"type": "integer"},
            "char_end": {"type": "integer"},
            "embedding_model": {"type": "keyword"},
        }

    @staticmethod
    def _chunk_index(chunk_id: str) -> int:
        marker = "chunk"
        position = chunk_id.rfind(marker)
        if position < 0:
            return 0
        try:
            return int(chunk_id[position + len(marker):])
        except ValueError:
            return 0

    @staticmethod
    def _print_progress(
        examined, total, indexed, created, updated, existing, started
    ):
        if examined == total or examined % 2560 == 0:
            elapsed = max(time.time() - started, 1e-9)
            print(
                f"  ES indexing: examined={examined}/{total}, "
                f"created={created}, updated={updated}, "
                f"existing_skip={existing}, failed=0, "
                f"write_rate={indexed / elapsed:.1f}, "
                f"created_rate={created / elapsed:.1f} chunks/s"
            )


class ElasticsearchRetriever:
    def __init__(
        self,
        backend: ElasticsearchBackend,
        embedder: Embedder,
        top_k: int = 10,
        candidate_k: int = 100,
        rrf_k: int = 60,
        query_prefix: str = "",
        collapse_recursive_partitions: bool = True,
    ):
        self.backend = backend
        self.embedder = embedder
        self.top_k = top_k
        self.candidate_k = max(top_k, candidate_k)
        self.rrf_k = rrf_k
        self.query_prefix = query_prefix
        self.collapse_recursive_partitions = collapse_recursive_partitions
        # Diagnostics only: populated by each retrieval call and consumed by
        # pipeline route traces.  It is never sent to the LLM.
        self.last_retrieval_trace: dict = {}

    @staticmethod
    def _base_chunk_id(chunk_id: str) -> str:
        """Map a Conan fallback partition to its cached parent chunk ID."""
        return re.sub(r"(?:__p\d+)+$", "", chunk_id)

    def _candidate_key(self, chunk_id: str) -> str:
        if not self.collapse_recursive_partitions:
            return chunk_id
        return self._base_chunk_id(chunk_id)

    def retrieve_bm25(self, query: str) -> list[RetrieveResult]:
        hits = self.backend.bm25_search(query, self.top_k)
        self.last_retrieval_trace = {
            "method": "bm25",
            "query": query,
            "top_k": self.top_k,
            "chunk_ids": [
                hit.get("_source", {}).get("chunk_id", hit.get("_id"))
                for hit in hits
            ],
            "document_ids": list(dict.fromkeys(
                hit.get("_source", {}).get("doc_id", "") for hit in hits
                if hit.get("_source", {}).get("doc_id", "")
            )),
        }
        return self._hits_to_results(hits)

    def retrieve_dense(self, query: str) -> list[RetrieveResult]:
        vector = self.embedder.encode([query], prefix=self.query_prefix)[0]
        hits = self.backend.dense_search(vector, self.top_k)
        self.last_retrieval_trace = {
            "method": "dense",
            "query": query,
            "top_k": self.top_k,
            "chunk_ids": [
                hit.get("_source", {}).get("chunk_id", hit.get("_id"))
                for hit in hits
            ],
            "document_ids": list(dict.fromkeys(
                hit.get("_source", {}).get("doc_id", "") for hit in hits
                if hit.get("_source", {}).get("doc_id", "")
            )),
        }
        return self._hits_to_results(hits)

    def retrieve_hybrid(
        self, query: str, dense_weight: float = 0.5, fusion_method: str = "rrf"
    ) -> list[RetrieveResult]:
        if fusion_method != "rrf":
            raise ValueError("Elasticsearch hybrid retrieval currently requires fusion_method=rrf")
        if not 0 <= dense_weight <= 1:
            raise ValueError("dense_weight must be between 0 and 1")
        vector = self.embedder.encode([query], prefix=self.query_prefix)[0]
        bm25 = self.backend.bm25_search(query, self.candidate_k)
        dense = self.backend.dense_search(vector, self.candidate_k)

        def trace_hits(hits: list[dict]) -> dict:
            return {
                "count": len(hits),
                "chunk_ids": [
                    hit.get("_source", {}).get("chunk_id", hit.get("_id"))
                    for hit in hits
                ],
                "document_ids": list(dict.fromkeys(
                    hit.get("_source", {}).get("doc_id", "") for hit in hits
                    if hit.get("_source", {}).get("doc_id", "")
                )),
            }

        self.last_retrieval_trace = {
            "method": "hybrid",
            "query": query,
            "candidate_k": self.candidate_k,
            "dense_weight": dense_weight,
            "fusion_method": fusion_method,
            "bm25": trace_hits(bm25),
            "dense": trace_hits(dense),
        }
        candidates: dict[str, tuple[dict, float]] = {}
        for weight, hits in ((1 - dense_weight, bm25), (dense_weight, dense)):
            for rank, hit in enumerate(hits, 1):
                chunk_id = hit.get("_source", {}).get("chunk_id", hit.get("_id"))
                candidate_key = self._candidate_key(chunk_id)
                previous = candidates.get(candidate_key)
                score = weight / (self.rrf_k + rank)
                # A recursively partitioned oversized cache chunk can produce
                # several ES vectors. Keep its strongest-ranked text as the
                # representative while fusing all partition evidence under
                # the one cache-level candidate, so it cannot crowd out
                # unrelated chunks before reranking/PageIndex.
                representative = hit
                if previous is not None:
                    representative = previous[0]
                candidates[candidate_key] = (
                    representative,
                    score + (previous[1] if previous else 0.0),
                )
        ranked = sorted(candidates.values(), key=lambda item: -item[1])[:self.top_k]
        self.last_retrieval_trace["rrf"] = {
            "count": len(ranked),
            "chunk_ids": [
                hit.get("_source", {}).get("chunk_id", hit.get("_id"))
                for hit, _ in ranked
            ],
            "document_ids": list(dict.fromkeys(
                hit.get("_source", {}).get("doc_id", "") for hit, _ in ranked
                if hit.get("_source", {}).get("doc_id", "")
            )),
        }
        return [self._hit_to_result(hit, score) for hit, score in ranked]

    def rerank(
        self,
        query: str,
        results: list[RetrieveResult],
        model_name: str,
        top_n: int,
        api_base: str,
        api_key_env: str = "",
        timeout: int = 120,
    ) -> list[RetrieveResult]:
        """Rerank ES candidates through an OpenAI-compatible /rerank API.

        The ES backend deliberately keeps retrieval and reranking separate:
        ES returns a broad hybrid candidate pool, while the remote cross
        encoder decides which passages should enter PageIndex and generation.
        """
        if not results:
            return []
        if not model_name:
            raise ValueError("reranker.model_name is required when reranking is enabled")
        if not api_base:
            raise ValueError("reranker.api_base is required for ES reranking")

        key = os.environ.get(api_key_env, "") if api_key_env else ""
        payload = {
            "model": model_name,
            "query": query,
            "documents": [result.text for result in results],
            "top_n": min(max(1, int(top_n)), len(results)),
            "return_documents": False,
        }
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        request = Request(
            f"{api_base.rstrip('/')}/rerank",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Rerank API error {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Rerank request failed: {exc}") from exc

        ranked_items = data.get("results", data.get("data", []))
        if not isinstance(ranked_items, list):
            raise RuntimeError("Rerank API returned no results list")

        reranked: list[RetrieveResult] = []
        seen_indices: set[int] = set()
        for item in ranked_items:
            if not isinstance(item, dict):
                continue
            raw_index = item.get("index", item.get("document_index"))
            try:
                index = int(raw_index)
            except (TypeError, ValueError):
                continue
            if not 0 <= index < len(results) or index in seen_indices:
                continue
            seen_indices.add(index)
            raw_score = item.get("relevance_score", item.get("score", 0.0))
            try:
                score = float(raw_score)
            except (TypeError, ValueError):
                score = 0.0
            result = results[index]
            reranked.append(RetrieveResult(
                chunk_id=result.chunk_id,
                doc_id=result.doc_id,
                source_type=result.source_type,
                text=result.text,
                score=score,
            ))

        if not reranked:
            raise RuntimeError("Rerank API returned no valid candidate indices")
        return reranked

    @staticmethod
    def get_parent_doc_ids(results: list[RetrieveResult]) -> list[str]:
        return list(dict.fromkeys(result.doc_id for result in results))

    @classmethod
    def _hits_to_results(cls, hits: list[dict]) -> list[RetrieveResult]:
        return [cls._hit_to_result(hit, float(hit.get("_score") or 0.0)) for hit in hits]

    @staticmethod
    def _hit_to_result(hit: dict, score: float) -> RetrieveResult:
        source = hit.get("_source", {})
        return RetrieveResult(
            chunk_id=source.get("chunk_id", hit.get("_id", "")),
            doc_id=source.get("doc_id", ""),
            source_type=source.get("source_type", ""),
            text=source.get("text", ""),
            score=float(score),
        )
