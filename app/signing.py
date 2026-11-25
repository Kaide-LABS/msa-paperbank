# -*- coding: utf-8 -*-
"""Backend-issued HMAC-signed download URLs (Phase 3).

A single, provider-neutral signing scheme: the backend signs an object `key` together
with an absolute expiry (`expires_at`, UNIX seconds) with HMAC-SHA256 under a secret
signing key, and later verifies the pair with a constant-time compare plus an expiry
check. The same scheme is used for the filesystem, MinIO and GCS adapters, so the
backend (never the storage provider) is the single verifier and AC 6's tamper/expiry
semantics hold identically everywhere.

No wall-clock is read at import time; `now` is injectable in every function so tests
need no real sleep. The signing secret and download base URL default to
`settings.url_signing_key` / `settings.download_base_url`, resolved lazily on first use
(never at import), but both may be passed explicitly (used by tests and by adapters that
carry their own configured values). This module imports no provider SDK.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import quote


def _signing_secret() -> str:
    """Resolve the HMAC signing secret from settings lazily (never at import)."""
    from app.config import settings

    return settings.url_signing_key.get_secret_value()


def _download_base_url() -> str:
    """Resolve the public download base URL from settings lazily (never at import)."""
    from app.config import settings

    return settings.download_base_url


def sign_key(key: str, expires_at: int, *, secret: str | None = None) -> str:
    """HMAC-SHA256 hex digest over ``f"{key}:{expires_at}"`` under the signing secret."""
    secret_value = secret if secret is not None else _signing_secret()
    message = f"{key}:{expires_at}".encode("utf-8")
    return hmac.new(secret_value.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify(
    key: str,
    expires_at: int,
    sig: str,
    *,
    secret: str | None = None,
    now: int | None = None,
) -> bool:
    """Accept iff the signature matches (constant-time) and the expiry is in the future.

    Rejects on any mismatch of ``key``, ``expires_at`` or ``sig`` and on ``expires_at <
    now``. ``now`` is injectable for tests; it defaults to the current UNIX time.
    """
    now_value = now if now is not None else int(time.time())
    if expires_at < now_value:
        return False
    expected = sign_key(key, expires_at, secret=secret)
    return hmac.compare_digest(expected, sig)


def signed_download_url(
    key: str,
    *,
    ttl_seconds: int = 900,
    secret: str | None = None,
    base_url: str | None = None,
    now: int | None = None,
) -> str:
    """Build a backend ``/download`` URL carrying ``key``, ``exp`` and ``sig``.

    The URL points at this backend's own download route (not a provider-native presigned
    URL), so verification is uniform and backend-controlled. Default TTL is ~15 minutes.
    """
    now_value = now if now is not None else int(time.time())
    expires_at = now_value + ttl_seconds
    sig = sign_key(key, expires_at, secret=secret)
    base = base_url if base_url is not None else _download_base_url()
    base = base.rstrip("/")
    return f"{base}/download?key={quote(key, safe='')}&exp={expires_at}&sig={sig}"
