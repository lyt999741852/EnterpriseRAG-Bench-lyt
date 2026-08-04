"""
Embedding interface -- abstract base with sentence-transformers, Ollama, and OpenAI-compatible backends.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import numpy as np


@dataclass
class EmbedderConfig:
    provider: str = "sentence_transformers"   # sentence_transformers | ollama | openai_compatible
    model_name: str = ""                      # e.g. "text-embedding-v4" for qwen
    device: str = "cpu"
    batch_size: int = 32
    dimension: int = 0                        # 0 = auto-detect
    revision: str = ""                        # immutable model revision when supported
    api_base: str = ""                        # for ollama / openai_compatible
    api_key_env: str = ""                     # env var for API key


class Embedder(ABC):
    """Abstract embedding client."""

    def __init__(self, config: EmbedderConfig):
        self.config = config

    @abstractmethod
    def encode(self, texts: list[str], show_progress: bool = False) -> np.ndarray:
        """Return (n_texts, dim) float32 array."""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        ...


# =========================================================================
# Sentence-Transformers backend
# =========================================================================

class SentenceTransformerEmbedder(Embedder):
    """sentence-transformers based embedder (local, no API needed)."""

    def __init__(self, config: EmbedderConfig):
        super().__init__(config)
        if not config.model_name:
            raise ValueError(
                "Embedding model_name is not configured. "
                "Set embedding.model_name in configs/default.yaml. "
                "Suggestion: 'all-MiniLM-L6-v2'"
            )
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(
            config.model_name,
            device=config.device,
            revision=config.revision or None,
        )
        self._dim = self._model.get_sentence_embedding_dimension()

    def encode(self, texts: list[str], show_progress: bool = False) -> np.ndarray:
        return self._model.encode(
            texts,
            batch_size=self.config.batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=True,
        )

    @property
    def dimension(self) -> int:
        return self._dim


# =========================================================================
# Ollama backend
# =========================================================================

class OllamaEmbedder(Embedder):
    """Ollama local embedding via HTTP API (POST /api/embed for batch).

    Recommended models:
      - nomic-embed-text   (~137M params, 768 dims)  -- good default
      - mxbai-embed-large  (~334M params, 1024 dims) -- stronger
      - bge-m3              (~567M params, 1024 dims) -- multilingual

    Uses /api/embed (batch) when available, falls back to /api/embeddings (single).
    """

    def __init__(self, config: EmbedderConfig):
        super().__init__(config)
        if not config.model_name:
            raise ValueError(
                "Embedding model_name is not configured for Ollama. "
                "Run 'ollama pull nomic-embed-text' first, then set "
                "embedding.model_name: 'nomic-embed-text' in config."
            )

        self._api_base = (config.api_base or "http://localhost:11434").rstrip("/")
        self._batch_size = config.batch_size or 16

        # Auto-detect dimension via batch endpoint
        test_vecs = self._call_batch(["warmup"])
        self._dim = test_vecs.shape[1]

        if config.dimension and config.dimension != self._dim:
            print(f"[WARNING] Config says dim={config.dimension}, "
                  f"but Ollama returned dim={self._dim}. Using {self._dim}.")

        print(f"Ollama embedder ready: model={config.model_name}, dim={self._dim}")

    def encode(self, texts: list[str], show_progress: bool = False) -> np.ndarray:
        all_vecs: list[np.ndarray] = []
        bs = self._batch_size

        for start in range(0, len(texts), bs):
            batch = texts[start:start + bs]
            vecs = self._call_batch(batch)
            all_vecs.append(vecs)

            if show_progress and (start + bs) % (bs * 10) == 0:
                print(f"  Ollama embedding: {min(start + bs, len(texts))}/{len(texts)}")

        vectors = np.vstack(all_vecs).astype(np.float32)

        # Normalize for cosine similarity (FAISS IndexFlatIP)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        vectors = vectors / norms

        return vectors

    def _call_batch(self, texts: list[str]) -> np.ndarray:
        """Call Ollama /api/embed (batch) or fall back to single /api/embeddings."""
        body = json.dumps({
            "model": self.config.model_name,
            "input": texts,
        }).encode("utf-8")

        req = Request(f"{self._api_base}/api/embed", data=body, headers={
            "Content-Type": "application/json",
        })

        try:
            with urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            # Response: {"model": "...", "embeddings": [[...], [...]]}
            return np.array(data.get("embeddings", []), dtype=np.float32)
        except HTTPError as e:
            # If /api/embed is not available (older Ollama), fall back to single
            if e.code == 404:
                return self._call_single_fallback(texts)
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama API error {e.code}: {detail}") from e
        except URLError as e:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self._api_base}. "
                f"Is it running? (ollama serve)"
            ) from e

    def _call_single_fallback(self, texts: list[str]) -> np.ndarray:
        """Fallback: call /api/embeddings once per text."""
        vecs = []
        for text in texts:
            body = json.dumps({
                "model": self.config.model_name,
                "prompt": text,
            }).encode("utf-8")

            req = Request(
                f"{self._api_base}/api/embeddings",
                data=body,
                headers={"Content-Type": "application/json"},
            )

            try:
                with urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                vecs.append(np.array(data["embedding"], dtype=np.float32))
            except HTTPError as e2:
                detail = e2.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Ollama API error {e2.code}: {detail}") from e2

        return np.array(vecs)

    @property
    def dimension(self) -> int:
        return self._dim


# =========================================================================
# OpenAI-compatible backend (Qwen, Ali Bailian, any /v1/embeddings API)
# =========================================================================

class OpenAICompatibleEmbedder(Embedder):
    """OpenAI-compatible embeddings API.

    Supports: Qwen (DashScope), OpenAI, vLLM, any /v1/embeddings endpoint.

    Example config for Qwen:
      provider: openai_compatible
      model_name: text-embedding-v4
      api_base: https://dashscope.aliyuncs.com/compatible-mode/v1
      api_key_env: DASHSCOPE_API_KEY
    """

    def __init__(self, config: EmbedderConfig):
        super().__init__(config)
        if not config.model_name:
            raise ValueError("embedding.model_name is required for openai_compatible")
        if not config.api_base:
            raise ValueError("embedding.api_base is required for openai_compatible")

        self._key = os.environ.get(config.api_key_env, "")
        self._api_url = f"{config.api_base.rstrip('/')}/embeddings"

        # Warmup: detect dimension
        test_vecs = self._call_api(["warmup"])
        self._dim = test_vecs.shape[1]
        print(f"OpenAI-compatible embedder: model={config.model_name}, dim={self._dim}")

    def encode(self, texts: list[str], show_progress: bool = False) -> np.ndarray:
        all_vecs: list[np.ndarray] = []
        bs = self.config.batch_size or 16

        for start in range(0, len(texts), bs):
            batch = texts[start:start + bs]
            vecs = self._call_api(batch)
            all_vecs.append(vecs)
            if show_progress:
                print(f"  Embedding: {min(start + bs, len(texts))}/{len(texts)}")

        vectors = np.vstack(all_vecs).astype(np.float32)

        # Normalize for FAISS IndexFlatIP
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        vectors = vectors / norms

        return vectors

    def _call_api(self, texts: list[str]) -> np.ndarray:
        body = json.dumps({
            "model": self.config.model_name,
            "input": texts,
            "encoding_format": "float",
        }).encode("utf-8")

        req = Request(self._api_url, data=body, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._key}",
        })

        try:
            with urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            # Response: {"data": [{"embedding": [...]}, ...]}
            items = sorted(data.get("data", []), key=lambda x: x.get("index", 0))
            return np.array([item["embedding"] for item in items], dtype=np.float32)
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Embedding API error {e.code}: {detail}") from e
        except URLError as e:
            raise RuntimeError(
                f"Cannot connect to embedding API at {self._api_url}"
            ) from e

    @property
    def dimension(self) -> int:
        return self._dim


# =========================================================================
# Fastembed backend (ONNX-optimized, 2-4x faster than sentence-transformers)
# =========================================================================

class FastembedEmbedder(Embedder):
    """Qdrant fastembed: ONNX-optimized, no API, 2-4x faster.

    Recommended models:
      - BAAI/bge-small-en-v1.5  (384 dim)  -- best quality/speed tradeoff
      - BAAI/bge-base-en-v1.5   (768 dim)  -- stronger
      - snowflake/snowflake-arctic-embed-xs (384 dim) -- fastest

    Install: pip install fastembed
    """

    def __init__(self, config: EmbedderConfig):
        super().__init__(config)
        if not config.model_name:
            raise ValueError("embedding.model_name required for fastembed")

        from fastembed import TextEmbedding
        self._model = TextEmbedding(
            model_name=config.model_name,
            threads=0,  # auto
        )
        # Detect dimension
        test = list(self._model.embed(["warmup"]))[0]
        self._dim = len(test)
        print(f"Fastembed ready: model={config.model_name}, dim={self._dim}")

    def encode(self, texts: list[str], show_progress: bool = False) -> np.ndarray:
        vecs = list(self._model.embed(
            texts,
            batch_size=self.config.batch_size or 256,
            show_progress_bar=show_progress,
        ))
        vectors = np.array(vecs, dtype=np.float32)

        # Normalize
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        vectors = vectors / norms

        return vectors

    @property
    def dimension(self) -> int:
        return self._dim


# =========================================================================
# Factory
# =========================================================================

def create_embedder(config: EmbedderConfig) -> Embedder:
    """Factory: return the right embedder for the configured provider."""
    if config.provider == "sentence_transformers":
        return SentenceTransformerEmbedder(config)
    if config.provider == "fastembed":
        return FastembedEmbedder(config)
    if config.provider == "ollama":
        return OllamaEmbedder(config)
    if config.provider == "openai_compatible":
        return OpenAICompatibleEmbedder(config)
    raise ValueError(f"Unknown embedding provider: {config.provider}")
