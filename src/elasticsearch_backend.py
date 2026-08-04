"""Elasticsearch vector indexing and retrieval for EnterpriseRAG-Bench."""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
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

    def index_chunks(
        self,
        chunks: list[Chunk],
        embedder: Embedder,
        max_chunks: int | None = None,
    ) -> dict:
        """Index missing chunks only; deterministic IDs make retries idempotent."""
        self.ensure_index(embedder.dimension)
        limit = len(chunks) if max_chunks is None else min(len(chunks), max_chunks)
        bulk_size = max(1, int(self.config.bulk_size))
        examined = existing = indexed = failed = 0
        started = time.time()

        for start in range(0, limit, bulk_size):
            batch = chunks[start:min(start + bulk_size, limit)]
            examined += len(batch)
            present = self._existing_ids([chunk.chunk_id for chunk in batch])
            missing = [chunk for chunk in batch if chunk.chunk_id not in present]
            existing += len(batch) - len(missing)
            if not missing:
                self._print_progress(examined, limit, indexed, existing, started)
                continue

            vectors = embedder.encode(
                [chunk.text for chunk in missing], show_progress=False
            ).astype(np.float32)
            if vectors.shape != (len(missing), embedder.dimension):
                raise RuntimeError(
                    f"Unexpected embedding shape {vectors.shape}; expected "
                    f"({len(missing)}, {embedder.dimension})"
                )
            if not np.isfinite(vectors).all():
                raise RuntimeError("Embedding output contains NaN or infinity")

            operations: list[str] = []
            for chunk, vector in zip(missing, vectors):
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
                if 200 <= int(detail.get("status", 500)) < 300:
                    indexed += 1
                else:
                    failed += 1
            if response.get("errors") or failed:
                errors = [
                    item.get("index", {}) for item in response.get("items", [])
                    if int(item.get("index", {}).get("status", 500)) >= 300
                ][:5]
                raise RuntimeError(f"Elasticsearch bulk indexing failed: {errors}")
            self._print_progress(examined, limit, indexed, existing, started)

        self._request("POST", f"/{self.config.index_name}/_refresh")
        duration = time.time() - started
        return {
            "examined": examined,
            "indexed": indexed,
            "existing": existing,
            "failed": failed,
            "duration_seconds": round(duration, 3),
            "chunks_per_second": round(indexed / duration, 2) if duration else 0,
            "index": self.config.index_name,
        }

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
        response = self._request("POST", f"/{self.config.alias_name}/_search", {
            "size": size,
            "_source": [
                "chunk_id", "doc_id", "source_type", "text", "chunk_index"
            ],
            "knn": {
                "field": "embedding",
                "query_vector": vector.astype(float).tolist(),
                "k": size,
                "num_candidates": max(size, min(10_000, size * 10)),
            },
        })
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
                "number_of_shards": 1,
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
    def _print_progress(examined, total, indexed, existing, started):
        if examined == total or examined % 2560 == 0:
            elapsed = max(time.time() - started, 1e-9)
            print(
                f"  ES indexing: {examined}/{total}, new={indexed}, "
                f"existing={existing}, new_rate={indexed / elapsed:.1f} chunks/s"
            )


class ElasticsearchRetriever:
    def __init__(
        self,
        backend: ElasticsearchBackend,
        embedder: Embedder,
        top_k: int = 10,
        candidate_k: int = 100,
        rrf_k: int = 60,
    ):
        self.backend = backend
        self.embedder = embedder
        self.top_k = top_k
        self.candidate_k = max(top_k, candidate_k)
        self.rrf_k = rrf_k

    def retrieve_bm25(self, query: str) -> list[RetrieveResult]:
        return self._hits_to_results(self.backend.bm25_search(query, self.top_k))

    def retrieve_dense(self, query: str) -> list[RetrieveResult]:
        vector = self.embedder.encode([query])[0]
        return self._hits_to_results(self.backend.dense_search(vector, self.top_k))

    def retrieve_hybrid(
        self, query: str, dense_weight: float = 0.5, fusion_method: str = "rrf"
    ) -> list[RetrieveResult]:
        if fusion_method != "rrf":
            raise ValueError("Elasticsearch hybrid retrieval currently requires fusion_method=rrf")
        if not 0 <= dense_weight <= 1:
            raise ValueError("dense_weight must be between 0 and 1")
        vector = self.embedder.encode([query])[0]
        bm25 = self.backend.bm25_search(query, self.candidate_k)
        dense = self.backend.dense_search(vector, self.candidate_k)
        candidates: dict[str, tuple[dict, float]] = {}
        for weight, hits in ((1 - dense_weight, bm25), (dense_weight, dense)):
            for rank, hit in enumerate(hits, 1):
                chunk_id = hit.get("_source", {}).get("chunk_id", hit.get("_id"))
                previous = candidates.get(chunk_id)
                score = weight / (self.rrf_k + rank)
                candidates[chunk_id] = (hit, score + (previous[1] if previous else 0.0))
        ranked = sorted(candidates.values(), key=lambda item: -item[1])[:self.top_k]
        return [self._hit_to_result(hit, score) for hit, score in ranked]

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
