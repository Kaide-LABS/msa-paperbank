# -*- coding: utf-8 -*-
"""Provider factory (Phase 1).

Each factory function returns the concrete adapter chosen by the active provider:
`get_object_store` / `get_embedder` / `get_engine_provider` switch on
`settings.provider`; `get_secrets_provider` switches on the `PROVIDER` env var directly
(the secrets loader runs before `Settings` is built, so it must not depend on it).

Only `"gcp"` is valid this phase; any other value raises `ValueError`. Adapter modules
are imported lazily inside each function so importing this package pulls in no vendor
SDK and opens no network client.
"""
from __future__ import annotations

import os

from app.ports import Embedder, EngineProvider, ObjectStore, SecretsProvider


def get_object_store(settings) -> ObjectStore:
    name = settings.provider
    if name == "gcp":
        from app.providers.gcp.storage import GcsObjectStore

        return GcsObjectStore.from_settings(settings)
    if name == "local":
        from app.providers.local.storage import FsObjectStore

        return FsObjectStore.from_settings(settings)
    if name == "minio":
        from app.providers.local.storage import MinioObjectStore

        return MinioObjectStore.from_settings(settings)
    raise ValueError(f"unknown provider: {name}")


def get_embedder(settings) -> Embedder:
    name = settings.provider
    if name == "gcp":
        from app.providers.gcp.embedder import GcpEmbedder

        return GcpEmbedder.from_settings(settings)
    raise ValueError(f"unknown provider: {name}")


def get_engine_provider(settings) -> EngineProvider:
    name = settings.provider
    if name == "gcp":
        from app.providers.gcp.engine import GcpEngineProvider

        return GcpEngineProvider(settings)
    raise ValueError(f"unknown provider: {name}")


def get_secrets_provider() -> SecretsProvider:
    name = os.environ.get("PROVIDER", "gcp")
    if name == "gcp":
        from app.providers.gcp.secrets import GcpSecretsProvider

        return GcpSecretsProvider()
    raise ValueError(f"unknown provider: {name}")
