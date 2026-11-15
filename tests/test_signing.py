"""Phase 3 Part A tests: HMAC-signed download URLs (`app.signing`), AC 6 / S1.

Pure crypto: `now` is injected (no real sleep), the signing secret is passed explicitly
(no settings dependency), and nothing touches the network.
"""
from urllib.parse import parse_qs, urlparse

from app import signing

SECRET = "unit-test-signing-secret"
BASE = "https://bot.example.test"


def test_verify_accepts_fresh_signature():
    exp = 1_000_000
    sig = signing.sign_key("papers/a.pdf", exp, secret=SECRET)
    assert signing.verify("papers/a.pdf", exp, sig, secret=SECRET, now=exp - 1) is True


def test_verify_rejects_expired():
    exp = 1_000_000
    sig = signing.sign_key("papers/a.pdf", exp, secret=SECRET)
    # now is past the expiry -> rejected even though the signature itself is valid.
    assert signing.verify("papers/a.pdf", exp, sig, secret=SECRET, now=exp + 1) is False


def test_verify_rejects_tampered_sig():
    exp = 1_000_000
    sig = signing.sign_key("papers/a.pdf", exp, secret=SECRET)
    tampered = ("0" if sig[0] != "0" else "1") + sig[1:]
    assert signing.verify("papers/a.pdf", exp, tampered, secret=SECRET, now=exp - 1) is False


def test_verify_rejects_tampered_key():
    exp = 1_000_000
    sig = signing.sign_key("papers/a.pdf", exp, secret=SECRET)
    assert signing.verify("papers/evil.pdf", exp, sig, secret=SECRET, now=exp - 1) is False


def test_verify_rejects_tampered_exp():
    exp = 1_000_000
    sig = signing.sign_key("papers/a.pdf", exp, secret=SECRET)
    assert signing.verify("papers/a.pdf", exp + 1, sig, secret=SECRET, now=exp - 1) is False


def test_verify_rejects_wrong_secret():
    exp = 1_000_000
    sig = signing.sign_key("papers/a.pdf", exp, secret=SECRET)
    assert signing.verify("papers/a.pdf", exp, sig, secret="other-secret", now=exp - 1) is False


def test_signed_download_url_roundtrips_through_verify():
    url = signing.signed_download_url(
        "papers/a b.pdf", ttl_seconds=900, secret=SECRET, base_url=BASE, now=1_000_000
    )
    parsed = urlparse(url)
    assert parsed.path == "/download"
    qs = parse_qs(parsed.query)
    assert qs["key"][0] == "papers/a b.pdf"
    exp = int(qs["exp"][0])
    assert exp == 1_000_000 + 900
    sig = qs["sig"][0]
    assert signing.verify(qs["key"][0], exp, sig, secret=SECRET, now=1_000_000) is True
    # and rejected after expiry
    assert signing.verify(qs["key"][0], exp, sig, secret=SECRET, now=exp + 1) is False
