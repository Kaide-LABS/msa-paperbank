"""Phase 3 Part A tests: `FsObjectStore` (filesystem `ObjectStore`), AC 6 / S2.

Uses a `tmp_path` root; no network. Signing secret / base URL are passed to the store
constructor so the test needs no settings.
"""
import pytest

from app import signing
from app.ports import ObjectStore
from app.providers.local.storage import FsObjectStore

SECRET = "fs-test-secret"
BASE = "https://bot.example.test"


def _store(tmp_path):
    return FsObjectStore(tmp_path, signing_secret=SECRET, download_base_url=BASE)


def test_is_objectstore(tmp_path):
    assert isinstance(_store(tmp_path), ObjectStore)


def test_roundtrip_upload_download_exists_delete(tmp_path):
    store = _store(tmp_path)
    key = "papers/mth102/2023.pdf"
    assert store.exists(key) is False
    store.upload_bytes(key, b"hello-pdf", content_type="application/pdf")
    assert store.exists(key) is True
    assert store.download_bytes(key) == b"hello-pdf"
    store.delete(key)
    assert store.exists(key) is False


def test_download_traversal_key_raises(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.download_bytes("../etc/passwd")


def test_download_absolute_key_raises(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.download_bytes("/etc/passwd")


def test_upload_traversal_key_raises(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.upload_bytes("../escape.txt", b"x")


def test_signed_url_verifies(tmp_path):
    store = _store(tmp_path)
    url = store.signed_url("papers/a.pdf", ttl_seconds=900)
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(url)
    assert parsed.netloc == "bot.example.test"
    assert parsed.path == "/download"
    qs = parse_qs(parsed.query)
    exp = int(qs["exp"][0])
    assert signing.verify(qs["key"][0], exp, qs["sig"][0], secret=SECRET, now=exp - 1) is True
