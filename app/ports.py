# -*- coding: utf-8 -*-
"""Provider-neutral ports (Phase 1).

Four structural `typing.Protocol` interfaces describing exactly the operations the
codebase performs today against GCS (object store), Vertex embeddings, Secret Manager
and Cloud SQL. Concrete adapters live in `app/providers/<provider>/`; a factory in
`app/providers/__init__.py` selects one by `settings.provider`.

These are `@runtime_checkable` so tests can assert conformance with `isinstance(...)`.
No heavy / vendor imports here: `sqlalchemy.Engine` is referenced only under
`TYPE_CHECKING` so importing this module never pulls in a provider SDK or opens a
network client.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # import only for typing; never at runtime
    from sqlalchemy import Engine


@runtime_checkable
class ObjectStore(Protocol):
    """Blob storage: the exact GCS operations the code uses today."""

    def download_bytes(self, key: str) -> bytes: ...

    def upload_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str | None = None,
        timeout: int | None = None,
    ) -> None: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...

    def signed_url(self, key: str, *, ttl_seconds: int = 900) -> str: ...


@runtime_checkable
class Embedder(Protocol):
    """Text embedding, mirroring `app.embeddings`."""

    def embed_one(self, text: str) -> list[float]: ...

    def embed_query(self, text: str) -> list[float]: ...

    def embed_documents(
        self, texts: list[str], concurrency: int | None = None
    ) -> list[list[float]]: ...

    @property
    def dim(self) -> int: ...


@runtime_checkable
class SecretsProvider(Protocol):
    """Resolve a single secret reference to its plaintext value."""

    def get(self, ref: str) -> str: ...


@runtime_checkable
class EngineProvider(Protocol):
    """Construct and dispose the SQLAlchemy engine for the non-test runtime."""

    def create_engine(self) -> "Engine": ...

    def dispose(self) -> None: ...
