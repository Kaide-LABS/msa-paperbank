# -*- coding: utf-8 -*-
"""Local object-store adapters (Phase 3).

`FsObjectStore` backs the `ObjectStore` port with a configured root directory on disk;
`MinioObjectStore` (optional, gated on the `minio` SDK) backs it with the S3 API. Both
issue signed download URLs through `app.signing` — a backend `/download` URL, never a
provider-native presigned URL — so verification is uniform and backend-controlled
(AC 6).

Neither opens a network client at import time: the MinIO client is built lazily in
`from_settings` / first use. `FsObjectStore` confines all reads/writes to its root and
rejects path-traversal keys (`..` or a leading separator).
"""
from __future__ import annotations

import os
from pathlib import Path


def _reject_traversal(key: str) -> None:
    """Reject keys that could escape the configured root (AC S2)."""
    if not key:
        raise ValueError("empty object key")
    # Normalise separators so a Windows-style backslash cannot sneak traversal through.
    normalized = key.replace("\\", "/")
    if normalized.startswith("/"):
        raise ValueError(f"absolute object key not allowed: {key!r}")
    parts = normalized.split("/")
    if ".." in parts:
        raise ValueError(f"path traversal not allowed in object key: {key!r}")
    # A drive-letter or UNC prefix is an absolute path on Windows.
    if os.path.splitdrive(key)[0]:
        raise ValueError(f"absolute object key not allowed: {key!r}")


class FsObjectStore:
    """`ObjectStore` backed by a filesystem root directory."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        signing_secret: str | None = None,
        download_base_url: str | None = None,
    ) -> None:
        self._root = Path(root).resolve()
        self._signing_secret = signing_secret
        self._download_base_url = download_base_url

    @classmethod
    def from_settings(cls, settings) -> "FsObjectStore":
        return cls(
            settings.storage_root,
            signing_secret=settings.url_signing_key.get_secret_value(),
            download_base_url=settings.download_base_url,
        )

    def _path(self, key: str) -> Path:
        _reject_traversal(key)
        resolved = (self._root / key).resolve()
        # Defence in depth: ensure the resolved path is still inside the root.
        if resolved != self._root and self._root not in resolved.parents:
            raise ValueError(f"object key escapes storage root: {key!r}")
        return resolved

    def download_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def upload_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str | None = None,
        timeout: int | None = None,
    ) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def exists(self, key: str) -> bool:
        try:
            return self._path(key).is_file()
        except ValueError:
            return False

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink()

    def signed_url(self, key: str, *, ttl_seconds: int = 900) -> str:
        from app.signing import signed_download_url

        return signed_download_url(
            key,
            ttl_seconds=ttl_seconds,
            secret=self._signing_secret,
            base_url=self._download_base_url,
        )


class MinioObjectStore:
    """`ObjectStore` backed by MinIO (S3 API). Optional: requires the `minio` SDK.

    Object operations go over the S3 API, but `signed_url` still goes through
    `app.signing` (a backend `/download` URL), not an S3 presign, so verification stays
    uniform and backend-controlled.
    """

    def __init__(
        self,
        client,
        bucket: str,
        *,
        signing_secret: str | None = None,
        download_base_url: str | None = None,
    ) -> None:
        self._client = client
        self._bucket = bucket
        self._signing_secret = signing_secret
        self._download_base_url = download_base_url

    @classmethod
    def from_settings(cls, settings) -> "MinioObjectStore":
        from minio import Minio

        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key.get_secret_value(),
            secret_key=settings.minio_secret_key.get_secret_value(),
            secure=getattr(settings, "minio_secure", True),
        )
        return cls(
            client,
            settings.minio_bucket,
            signing_secret=settings.url_signing_key.get_secret_value(),
            download_base_url=settings.download_base_url,
        )

    def download_bytes(self, key: str) -> bytes:
        response = self._client.get_object(self._bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def upload_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str | None = None,
        timeout: int | None = None,
    ) -> None:
        import io

        self._client.put_object(
            self._bucket,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type or "application/octet-stream",
        )

    def exists(self, key: str) -> bool:
        from minio.error import S3Error

        try:
            self._client.stat_object(self._bucket, key)
            return True
        except S3Error:
            return False

    def delete(self, key: str) -> None:
        self._client.remove_object(self._bucket, key)

    def signed_url(self, key: str, *, ttl_seconds: int = 900) -> str:
        from app.signing import signed_download_url

        return signed_download_url(
            key,
            ttl_seconds=ttl_seconds,
            secret=self._signing_secret,
            base_url=self._download_base_url,
        )
