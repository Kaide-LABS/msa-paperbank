# -*- coding: utf-8 -*-
"""GCP embedder adapter (Phase 1).

Implements the `Embedder` port by delegating to the existing `app.embeddings`
functions (lazy import — no logic duplication). `task_type` RETRIEVAL_QUERY /
RETRIEVAL_DOCUMENT and the dimension check stay in `app.embeddings`.
"""
from __future__ import annotations


class GcpEmbedder:
    """`Embedder` delegating to `app.embeddings` (Vertex / google-genai)."""

    def __init__(self, dim: int) -> None:
        self._dim = dim

    @classmethod
    def from_settings(cls, settings) -> "GcpEmbedder":
        return cls(settings.embedding_dim)

    def embed_one(self, text: str) -> list[float]:
        from app import embeddings

        return embeddings.embed_one(text)

    def embed_query(self, text: str) -> list[float]:
        from app import embeddings

        return embeddings.embed_query(text)

    def embed_documents(
        self, texts: list[str], concurrency: int | None = None
    ) -> list[list[float]]:
        from app import embeddings

        return embeddings.embed_many(texts, concurrency=concurrency)

    @property
    def dim(self) -> int:
        return self._dim
