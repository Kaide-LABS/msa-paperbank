# -*- coding: utf-8 -*-
"""Bearer-token auth for the future retrieval tool endpoint (Phase 3).

`require_tool_token` is a FastAPI dependency that compares the `Authorization: Bearer …`
header to `settings.tool_api_token` with a constant-time compare. It fails closed: a
missing header, a wrong scheme, or a non-matching token is a 401 — never a 500 and never
an unauthenticated pass-through (AC S4). The token is sourced from settings, never a
literal.
"""
from __future__ import annotations

import hmac

from fastapi import Header, HTTPException


def _configured_token() -> str | None:
    """Resolve the tool API token from settings lazily (never at import)."""
    from app.config import settings

    token = getattr(settings, "tool_api_token", None)
    if token is None:
        return None
    # `SecretStr` or a plain string, tolerated either way.
    get = getattr(token, "get_secret_value", None)
    return get() if callable(get) else str(token)


def require_tool_token(authorization: str = Header(default="")) -> None:
    """FastAPI dependency: 401 unless the Bearer token exactly matches the configured one."""
    configured = _configured_token()
    if not configured:
        # No token configured -> the endpoint is closed, not open.
        raise HTTPException(status_code=401, detail="tool endpoint not configured")
    scheme, _, presented = authorization.partition(" ")
    if scheme.lower() != "bearer" or not presented:
        raise HTTPException(status_code=401, detail="missing or malformed bearer token")
    if not hmac.compare_digest(presented, configured):
        raise HTTPException(status_code=401, detail="invalid token")
