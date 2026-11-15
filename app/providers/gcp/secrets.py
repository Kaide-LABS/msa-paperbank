# -*- coding: utf-8 -*-
"""GCP secrets adapter (Phase 1).

Implements the `SecretsProvider` port over Secret Manager. The client is constructed
lazily on first `get(...)`, never at import, so importing this module makes no network
call and the loader is a genuine no-op when secret loading is disabled.
"""
from __future__ import annotations


class GcpSecretsProvider:
    """`SecretsProvider` backed by Google Secret Manager."""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google.cloud import secretmanager

            self._client = secretmanager.SecretManagerServiceClient()
        return self._client

    def get(self, ref: str) -> str:
        response = self._get_client().access_secret_version(name=ref)
        return response.payload.data.decode("UTF-8")
