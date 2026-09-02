"""
Retriever: BM25, Dense, and Hybrid retrieval over indexed chunks.
Returns deduplicated parent doc IDs for evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .indexer import Indexer, _simple_tokenize
from .embedder import Embedder


@dataclass
class RetrieveResult:
    chunk_id: str
    doc_id: str
    source_type: str
    text: str
    score: float


class Retriever:
    def __init__(
        self,
        indexer: Indexer,
        embedder: Embedder | None,
        top_k: int = 10,
        candidate_k: int = 100,
        rrf_k: int = 60,
        query_prefix: str = "",
    ):
        self.indexer = indexer
        self.embedder = embedder
        self.top_k = top_k
        self.candidate_k = max(top_k, candidate_k)
        self.rrf_k = rrf_k
        self.query_prefix = query_prefix
        self._rerankers: dict[str, object] = {}
        self.last_retrieval_trace: dict = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retrieve_bm25(self, query: str) -> list[RetrieveResult]:
        tokens = _simple_tokenize(query)
        scores = self.indexer.bm25.get_scores(tokens)
        results = self._top_k_results(scores)
        self.last_retrieval_trace = self._trace_results("bm25", query, results)
        return results

    def retrieve_dense(self, query: str) -> list[RetrieveResult]:
        if self.embedder is None:
            raise RuntimeError("Dense retrieval requires an embedder")
        q_vec = self.embedder.encode(
            [query], prefix=self.query_prefix
        )[0].astype(np.float32).reshape(1, -1)
        distances, indices = self.indexer.faiss_index.search(q_vec, self.top_k)
        results = self._faiss_to_results(indices[0], distances[0])
        self.last_retrieval_trace = self._trace_results("dense", query, results)
        return results

    def retrieve_hybrid(
        self,
        query: str,
        dense_weight: float = 0.5,
        fusion_method: str = "rrf",
    ) -> list[RetrieveResult]:
        """Fuse BM25 and dense candidates using RRF or legacy linear fusion."""
        if self.embedder is None:
            raise RuntimeError("Hybrid retrieval requires an embedder")
        # BM25
        bm25_tokens = _simple_tokenize(query)
        bm25_scores = self.indexer.bm25.get_scores(bm25_tokens)

        # Dense
        q_vec = self.embedder.encode(
            [query], prefix=self.query_prefix
        )[0].astype(np.float32).reshape(1, -1)
        n = self.indexer.faiss_index.ntotal
        dense_k = min(n, self.candidate_k)
        distances, indices = self.indexer.faiss_index.search(q_vec, dense_k)

        if fusion_method == "rrf":
            bm25_indices = self._top_indices(bm25_scores, self.candidate_k)
            fused_by_index: dict[int, float] = {}
            for rank, idx in enumerate(bm25_indices, 1):
                fused_by_index[int(idx)] = 1.0 / (self.rrf_k + rank)
            for rank, idx in enumerate(indices[0], 1):
                if idx >= 0:
                    fused_by_index[int(idx)] = (
                        fused_by_index.get(int(idx), 0.0)
                        + 1.0 / (self.rrf_k + rank)
                    )
            ranked = sorted(
                fused_by_index.items(), key=lambda item: (-item[1], item[0])
            )[:self.top_k]
            results = self._index_score_pairs_to_results(ranked)
            self.last_retrieval_trace = self._trace_results("hybrid_rrf", query, results)
            return results

        if fusion_method != "linear":
            raise ValueError(f"Unknown hybrid fusion method: {fusion_method}")

        # Build full dense scores array
        dense_scores = np.zeros(len(self.indexer.chunks))
        for idx, dist in zip(indices[0], distances[0]):
            if idx >= 0:
                dense_scores[idx] = dist

        # Normalize
        bm25_norm = self._minmax_norm(bm25_scores)
        dense_norm = self._minmax_norm(dense_scores)

        fused = (1 - dense_weight) * bm25_norm + dense_weight * dense_norm
        results = self._top_k_results(fused)
        self.last_retrieval_trace = self._trace_results("hybrid_linear", query, results)
        return results

    @staticmethod
    def _trace_results(method: str, query: str, results: list[RetrieveResult]) -> dict:
        return {
            "method": method,
            "query": query,
            "count": len(results),
            "chunk_ids": [item.chunk_id for item in results],
            "document_ids": list(dict.fromkeys(item.doc_id for item in results)),
        }

    def get_parent_doc_ids(self, results: list[RetrieveResult]) -> list[str]:
        """Extract unique parent doc IDs, preserving order."""
        seen = set()
        doc_ids = []
        for r in results:
            if r.doc_id not in seen:
                seen.add(r.doc_id)
                doc_ids.append(r.doc_id)
        return doc_ids

    def rerank(
        self,
        query: str,
        results: list[RetrieveResult],
        model_name: str,
        top_n: int,
    ) -> list[RetrieveResult]:
        """Cross-encoder reranking, loaded lazily only when configured."""
        if not results:
            return []
        if not model_name:
            raise ValueError("reranker.model_name is required when reranking is enabled")
        if model_name not in self._rerankers:
            from sentence_transformers import CrossEncoder
            self._rerankers[model_name] = CrossEncoder(model_name)
        model = self._rerankers[model_name]
        scores = model.predict([(query, result.text) for result in results])
        ranked = sorted(
            zip(results, scores), key=lambda item: float(item[1]), reverse=True
        )[:top_n]
        return [
            RetrieveResult(
                chunk_id=result.chunk_id,
                doc_id=result.doc_id,
                source_type=result.source_type,
                text=result.text,
                score=float(score),
            )
            for result, score in ranked
        ]

    def expand_neighbors(
        self,
        results: list[RetrieveResult],
        neighbor_chunks: int = 1,
    ) -> list[RetrieveResult]:
        """Expand hits with adjacent chunks from the same parent document."""
        if neighbor_chunks <= 0 or not results:
            return results
        positions = {chunk.chunk_id: i for i, chunk in enumerate(self.indexer.chunks)}
        seen: set[str] = set()
        expanded: list[RetrieveResult] = []
        for result in results:
            index = positions.get(result.chunk_id)
            candidates: list[tuple[int, float]] = []
            if index is not None:
                for offset in range(-neighbor_chunks, neighbor_chunks + 1):
                    candidate_index = index + offset
                    if not 0 <= candidate_index < len(self.indexer.chunks):
                        continue
                    chunk = self.indexer.chunks[candidate_index]
                    if chunk.doc_id != result.doc_id:
                        continue
                    candidates.append((candidate_index, result.score - abs(offset) * 1e-6))
            for candidate_index, score in candidates:
                chunk = self.indexer.chunks[candidate_index]
                if chunk.chunk_id in seen:
                    continue
                seen.add(chunk.chunk_id)
                expanded.append(RetrieveResult(
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    source_type=chunk.source_type,
                    text=chunk.text,
                    score=score,
                ))
        return expanded

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _top_k_results(self, scores: np.ndarray) -> list[RetrieveResult]:
        top_indices = self._top_indices(scores, self.top_k)

        results = []
        for idx in top_indices:
            chunk = self.indexer.chunks[int(idx)]
            results.append(RetrieveResult(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                source_type=chunk.source_type,
                text=chunk.text,
                score=float(scores[idx]),
            ))
        return results

    @staticmethod
    def _top_indices(scores: np.ndarray, count: int) -> np.ndarray:
        k = min(count, len(scores))
        if k <= 0:
            return np.array([], dtype=np.int64)
        top_indices = np.argpartition(scores, -k)[-k:]
        return top_indices[np.argsort(-scores[top_indices])]

    def _index_score_pairs_to_results(
        self, pairs: list[tuple[int, float]]
    ) -> list[RetrieveResult]:
        results = []
        for idx, score in pairs:
            chunk = self.indexer.chunks[idx]
            results.append(RetrieveResult(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                source_type=chunk.source_type,
                text=chunk.text,
                score=float(score),
            ))
        return results

    def _faiss_to_results(
        self, indices: np.ndarray, distances: np.ndarray
    ) -> list[RetrieveResult]:
        results = []
        for idx, dist in zip(indices, distances):
            if idx < 0:
                continue
            chunk = self.indexer.chunks[int(idx)]
            results.append(RetrieveResult(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                source_type=chunk.source_type,
                text=chunk.text,
                score=float(dist),
            ))
        return results

    @staticmethod
    def _minmax_norm(arr: np.ndarray) -> np.ndarray:
        mn, mx = arr.min(), arr.max()
        if mx == mn:
            return np.zeros_like(arr)
        return (arr - mn) / (mx - mn)
