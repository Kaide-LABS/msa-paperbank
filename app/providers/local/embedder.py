# -*- coding: utf-8 -*-
"""Local CPU embedder adapter (Phase 4).

Implements the `Embedder` port over a `sentence-transformers` model
(`all-mpnet-base-v2` class, native 768-dim, CPU). The point of this adapter is to
remove the backend's last model-API dependency: it runs a small model on the
school's own hardware instead of calling Vertex, while keeping the `Vector(768)`
schema and the HNSW / `pg_trgm` indexes unchanged.

Two invariants this module guarantees (AC 2 / E1):
- importing this module pulls in **no** model weights and makes **no** network call:
  `sentence_transformers` is imported lazily inside `_get_encoder`, never at module
  import and never at construction;
- the encoder is **injectable** so unit tests pass a deterministic fake and never
  download a model.

The model `all-mpnet-base-v2` is symmetric (no RETRIEVAL_QUERY / RETRIEVAL_DOCUMENT
task split), so `embed_query` and `embed_documents` use the same encoding. Vectors
are L2-normalized (E4) so the existing `cosine_distance` ordering stays valid; a
dimension mismatch raises `EmbeddingError`, mirroring `app.embeddings`.
"""
from __future__ import annotations

import math

from app.errors import EmbeddingError


class LocalCpuEmbedder:
    """`Embedder` over a lazily-loaded `sentence-transformers` CPU model."""

    def __init__(
        self,
        encoder=None,
        *,
        dim: int = 768,
        normalize: bool = True,
        batch_size: int = 32,
        model_name: str | None = None,
        model_path: str | None = None,
        device: str = "cpu",
    ) -> None:
        # `encoder` is an already-loaded model object (real SentenceTransformer or a
        # test fake exposing `.encode`). When None, the real model is built lazily on
        # first encode via `_get_encoder` — never here, never at import.
        self._encoder = encoder
        self._dim = dim
        self._normalize = normalize
        self._batch_size = batch_size
        self._model_name = model_name
        self._model_path = model_path
        self._device = device

    @classmethod
    def from_settings(cls, settings) -> "LocalCpuEmbedder":
        return cls(
            encoder=None,
            dim=settings.embedding_dim,
            normalize=settings.embedding_normalize,
            batch_size=settings.embedding_batch_size,
            model_name=settings.embedding_model_name,
            model_path=settings.embedding_model_path,
            device=settings.embedding_device,
        )

    def _get_encoder(self):
        if self._encoder is None:
            # Lazy, first-encode only: this is the single place `sentence_transformers`
            # is imported and the model is loaded. A pre-downloaded local path (for an
            # offline server) is preferred over the hub name when set.
            from sentence_transformers import SentenceTransformer

            source = self._model_path or self._model_name
            self._encoder = SentenceTransformer(source, device=self._device)
        return self._encoder

    def _to_vec(self, raw) -> list[float]:
        vec = [float(x) for x in raw]
        if self._normalize:
            norm = math.sqrt(sum(x * x for x in vec))
            if norm > 0:
                vec = [x / norm for x in vec]
        if len(vec) != self._dim:
            raise EmbeddingError(f"Expected dim {self._dim}, got {len(vec)}")
        return vec

    def embed_one(self, text: str) -> list[float]:
        enc = self._get_encoder()
        out = enc.encode(
            [text], normalize_embeddings=self._normalize, batch_size=self._batch_size
        )
        return self._to_vec(out[0])

    def embed_query(self, text: str) -> list[float]:
        # all-mpnet-base-v2 is symmetric: query and document encoding are identical.
        return self.embed_one(text)

    def embed_documents(
        self, texts: list[str], concurrency: int | None = None
    ) -> list[list[float]]:
        if not texts:
            return []
        enc = self._get_encoder()
        out = enc.encode(
            list(texts),
            normalize_embeddings=self._normalize,
            batch_size=self._batch_size,
        )
        return [self._to_vec(row) for row in out]

    @property
    def dim(self) -> int:
        return self._dim
