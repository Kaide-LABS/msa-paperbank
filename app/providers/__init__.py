# -*- coding: utf-8 -*-
"""Provider factory (Phase 1).

Each factory function returns the concrete adapter chosen by the active provider:
`get_object_store` / `get_embedder` / `get_engine_provider` switch on
`settings.provider`; `get_secrets_provider` switches on the `PROVIDER` env var directly
(the secrets loader runs before `Settings` is built, so it must not depend on it).

Only `"local"`/`"minio"` are valid; any other value (including the retired `"gcp"`)
raises `ValueError`. Adapter modules are imported lazily inside each function so importing
this package pulls in no vendor SDK and opens no network client.
"""
from __future__ import annotations

import os

from app.ports import Embedder, EngineProvider, ObjectStore, SecretsProvider


def get_object_store(settings) -> ObjectStore:
    name = settings.provider
    if name == "local":
        from app.providers.local.storage import FsObjectStore

        return FsObjectStore.from_settings(settings)
    if name == "minio":
        from app.providers.local.storage import MinioObjectStore

        return MinioObjectStore.from_settings(settings)
    raise ValueError(f"unknown provider: {name}")


def get_embedder(settings) -> Embedder:
    name = settings.provider
    if name in {"local", "minio"}:
        from app.providers.local.embedder import LocalCpuEmbedder

        return LocalCpuEmbedder.from_settings(settings)
    raise ValueError(f"unknown provider: {name}")


def get_engine_provider(settings) -> EngineProvider:
    name = settings.provider
    if name in {"local", "minio"}:
        from app.providers.local.engine import PostgresEngineProvider

        return PostgresEngineProvider(settings)
    raise ValueError(f"unknown provider: {name}")


def get_secrets_provider(settings=None) -> SecretsProvider:
    name = getattr(settings, "provider", None) or os.environ.get("PROVIDER", "local")
    if name in {"local", "minio"}:
        from app.providers.local.secrets import EnvSecretsProvider, FileSecretsProvider

        secrets_dir = getattr(settings, "secrets_dir", None) if settings is not None else None
        return FileSecretsProvider(secrets_dir) if secrets_dir else EnvSecretsProvider()
    raise ValueError(f"unknown provider: {name}")
