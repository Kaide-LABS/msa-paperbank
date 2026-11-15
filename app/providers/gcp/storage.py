# -*- coding: utf-8 -*-
"""GCP object-store adapter (Phase 1).

Thin wrapper over `google.cloud.storage` that implements the `ObjectStore` port by
delegating to `bucket.blob(key).*`. The underlying `storage.Client` is built lazily
(in `from_settings` / first use) and never at import, so importing this module makes
no network call.
"""
from __future__ import annotations


class GcsObjectStore:
    """`ObjectStore` backed by a GCS bucket."""

    def __init__(self, client, bucket_name: str) -> None:
        self._client = client
        self._bucket_name = bucket_name

    @classmethod
    def from_settings(cls, settings) -> "GcsObjectStore":
        from google.cloud import storage

        bucket = getattr(settings, "object_store_bucket", settings.gcs_bucket)
        return cls(storage.Client(project=settings.gcp_project), bucket)

    def _blob(self, key: str):
        return self._client.bucket(self._bucket_name).blob(key)

    def download_bytes(self, key: str) -> bytes:
        return self._blob(key).download_as_bytes()

    def upload_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str | None = None,
        timeout: int | None = None,
    ) -> None:
        if timeout is None:
            self._blob(key).upload_from_string(data, content_type=content_type)
        else:
            self._blob(key).upload_from_string(
                data, content_type=content_type, timeout=timeout
            )

    def exists(self, key: str) -> bool:
        return self._blob(key).exists()

    def delete(self, key: str) -> None:
        self._blob(key).delete()

    def signed_url(self, key: str, *, ttl_seconds: int = 900) -> str:
        # Uniform across adapters: return a backend `/download` URL (HMAC-signed by
        # `app.signing`), not a GCS-native presigned URL, so the backend stays the sole
        # verifier. The live WhatsApp path still sends bytes; this exists so the port is
        # uniform and the download route works under any provider.
        from app.signing import signed_download_url

        return signed_download_url(key, ttl_seconds=ttl_seconds)
