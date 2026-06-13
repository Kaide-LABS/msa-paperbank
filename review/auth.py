# -*- coding: utf-8 -*-
"""Review-panel auth: whitelisted phone + WhatsApp OTP -> HMAC-signed session cookie.

A phone number is a username, not a secret — the OTP (delivered to the number via the same
WhatsApp send path the bot uses) is what authenticates. Codes are stored HASHED with a short TTL
and an attempt cap; the session cookie is HttpOnly+Secure and HMAC-signed."""
import hmac
import hashlib
import base64
import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from app.config import settings

COOKIE = "pbreview"


def _secret() -> bytes:
    s = settings.review_session_secret.get_secret_value() if settings.review_session_secret else "dev-insecure-change-me"
    return s.encode()


# ---------------------------------------------------------------- session cookie
def issue_session(phone: str) -> str:
    exp = int((datetime.now(timezone.utc) + timedelta(hours=settings.review_session_hours)).timestamp())
    payload = f"{phone}|{exp}".encode()
    sig = hmac.new(_secret(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload).decode() + "." + base64.urlsafe_b64encode(sig).decode()


def read_session(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    try:
        p_b64, s_b64 = token.split(".", 1)
        payload = base64.urlsafe_b64decode(p_b64)
        sig = base64.urlsafe_b64decode(s_b64)
        if not hmac.compare_digest(sig, hmac.new(_secret(), payload, hashlib.sha256).digest()):
            return None
        phone, exp = payload.decode().split("|")
        if int(exp) < int(datetime.now(timezone.utc).timestamp()):
            return None
        return phone
    except Exception:
        return None


# ---------------------------------------------------------------- reviewers + OTP
def active_reviewer(session, phone: str) -> dict | None:
    r = session.execute(text("SELECT phone, name, role FROM reviewers WHERE phone=:p AND active"),
                        {"p": phone}).mappings().first()
    return dict(r) if r else None


def _hash_code(phone: str, code: str) -> str:
    return hmac.new(_secret(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def can_request(session, phone: str) -> bool:
    """Rate-limit: refuse a new code within review_otp_resend_seconds of the last."""
    r = session.execute(text("SELECT created_at FROM review_otp WHERE phone=:p"), {"p": phone}).mappings().first()
    if not r or r["created_at"] is None:
        return True
    return r["created_at"] < datetime.now(timezone.utc) - timedelta(seconds=settings.review_otp_resend_seconds)


def issue_otp(session, phone: str) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    exp = datetime.now(timezone.utc) + timedelta(seconds=settings.review_otp_ttl_seconds)
    session.execute(text(
        "INSERT INTO review_otp (phone, code_hash, expires_at, attempts, locked, created_at) "
        "VALUES (:p, :h, :e, 0, false, now()) "
        "ON CONFLICT (phone) DO UPDATE SET code_hash=:h, expires_at=:e, attempts=0, locked=false, created_at=now()"
    ), {"p": phone, "h": _hash_code(phone, code), "e": exp})
    session.commit()
    return code


def verify_otp(session, phone: str, code: str) -> bool:
    r = session.execute(text("SELECT code_hash, expires_at, attempts, locked FROM review_otp WHERE phone=:p"),
                        {"p": phone}).mappings().first()
    if not r or r["locked"] or r["expires_at"] < datetime.now(timezone.utc):
        return False
    if hmac.compare_digest(r["code_hash"], _hash_code(phone, code or "")):
        session.execute(text("DELETE FROM review_otp WHERE phone=:p"), {"p": phone})
        session.commit()
        return True
    attempts = r["attempts"] + 1
    session.execute(text("UPDATE review_otp SET attempts=:a, locked=:l WHERE phone=:p"),
                    {"a": attempts, "l": attempts >= settings.review_otp_max_attempts, "p": phone})
    session.commit()
    return False
