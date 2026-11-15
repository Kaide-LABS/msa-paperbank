# -*- coding: utf-8 -*-
"""Phase 1 unit tests: ports, GCP adapters, and the provider factory.

No test here performs a network call: the object-store adapter is driven with a
MagicMock `storage.Client`, the embedder delegates to a patched `app.embeddings`, and
the factory is checked without ever calling `create_engine` (no DB connect).
"""
import types
from unittest.mock import MagicMock, patch

import pytest

from app.ports import ObjectStore, Embedder, SecretsProvider, EngineProvider
from app.providers import (
    get_object_store,
    get_embedder,
    get_engine_provider,
    get_secrets_provider,
)
from app.providers.gcp.storage import GcsObjectStore
from app.providers.gcp.embedder import GcpEmbedder
from app.providers.gcp.engine import GcpEngineProvider
from app.providers.gcp.secrets import GcpSecretsProvider


# --------------------------------------------------------------------------- fakes
class FakeObjectStore:
    """In-memory ObjectStore used to prove the port is satisfiable without GCS."""

    def __init__(self):
        self._data: dict[str, bytes] = {}

    def download_bytes(self, key: str) -> bytes:
        if key not in self._data:
            raise KeyError(key)
        return self._data[key]

    def upload_bytes(self, key, data, content_type=None, timeout=None) -> None:
        self._data[key] = data

    def exists(self, key: str) -> bool:
        return key in self._data

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


def _settings(**over):
    base = dict(provider="gcp", gcp_project="proj", gcs_bucket="bucket", embedding_dim=768)
    base.update(over)
    return types.SimpleNamespace(**base)


# --------------------------------------------------------------------------- ObjectStore port
def test_fake_object_store_roundtrip_and_isinstance():
    fake = FakeObjectStore()
    assert isinstance(fake, ObjectStore)  # runtime-checkable structural conformance

    fake.upload_bytes("k", b"hello", content_type="text/plain")
    assert fake.download_bytes("k") == b"hello"
    assert fake.exists("k") is True
    fake.delete("k")
    assert fake.exists("k") is False


# --------------------------------------------------------------------------- GcsObjectStore adapter
def test_gcs_object_store_translates_calls():
    client = MagicMock()
    blob = client.bucket.return_value.blob.return_value

    store = GcsObjectStore(client, "bucket")
    assert isinstance(store, ObjectStore)

    blob.download_as_bytes.return_value = b"pdf"
    assert store.download_bytes("obj") == b"pdf"
    client.bucket.assert_called_with("bucket")
    client.bucket.return_value.blob.assert_called_with("obj")

    store.upload_bytes("obj", b"data", content_type="application/pdf")
    blob.upload_from_string.assert_called_with(b"data", content_type="application/pdf")

    # timeout, when supplied, is forwarded; omitted entirely when None
    store.upload_bytes("obj", b"data", content_type="application/pdf", timeout=600)
    blob.upload_from_string.assert_called_with(
        b"data", content_type="application/pdf", timeout=600
    )

    blob.exists.return_value = True
    assert store.exists("obj") is True
    blob.exists.assert_called_once()

    store.delete("obj")
    blob.delete.assert_called_once()


def test_gcs_object_store_constructor_opens_no_client():
    # Constructing the adapter must not build a real storage.Client.
    with patch("google.cloud.storage.Client") as mock_client:
        GcsObjectStore(MagicMock(), "bucket")
        mock_client.assert_not_called()


def test_gcs_object_store_from_settings_builds_client_lazily():
    with patch("google.cloud.storage.Client") as mock_client:
        store = GcsObjectStore.from_settings(_settings())
        mock_client.assert_called_once_with(project="proj")
        assert isinstance(store, GcsObjectStore)


# --------------------------------------------------------------------------- GcpEmbedder adapter
def test_gcp_embedder_delegates_and_dim():
    # Patch the functions on the real app.embeddings module so delegation is asserted
    # regardless of import order (GcpEmbedder does `from app import embeddings`).
    with patch("app.embeddings.embed_one", return_value=[0.1] * 768) as m_one, \
         patch("app.embeddings.embed_query", return_value=[0.2] * 768) as m_query, \
         patch("app.embeddings.embed_many", return_value=[[0.3] * 768]) as m_many:
        emb = GcpEmbedder(768)
        assert isinstance(emb, Embedder)
        assert emb.dim == 768

        assert emb.embed_one("x") == [0.1] * 768
        m_one.assert_called_once_with("x")

        assert emb.embed_query("q") == [0.2] * 768
        m_query.assert_called_once_with("q")

        assert emb.embed_documents(["a"], concurrency=4) == [[0.3] * 768]
        m_many.assert_called_once_with(["a"], concurrency=4)


# --------------------------------------------------------------------------- factory
def test_factory_returns_gcp_adapters():
    s = _settings()
    assert isinstance(get_object_store(s), GcsObjectStore)
    assert isinstance(get_embedder(s), GcpEmbedder)

    ep = get_engine_provider(s)
    assert isinstance(ep, GcpEngineProvider)
    # the port is satisfied; create_engine is NOT called (no DB connect in a unit test)
    assert isinstance(ep, EngineProvider)


def test_get_secrets_provider_gcp(monkeypatch):
    monkeypatch.delenv("PROVIDER", raising=False)  # default -> gcp
    sp = get_secrets_provider()
    assert isinstance(sp, GcpSecretsProvider)
    assert isinstance(sp, SecretsProvider)


def test_factory_unknown_provider_raises():
    s = _settings(provider="local")
    with pytest.raises(ValueError, match="unknown provider: local"):
        get_object_store(s)
    with pytest.raises(ValueError, match="unknown provider: local"):
        get_embedder(s)
    with pytest.raises(ValueError, match="unknown provider: local"):
        get_engine_provider(s)


def test_get_secrets_provider_unknown_raises(monkeypatch):
    monkeypatch.setenv("PROVIDER", "local")
    with pytest.raises(ValueError, match="unknown provider: local"):
        get_secrets_provider()


def test_default_provider_setting_is_gcp():
    from app.config import settings

    assert settings.provider == "gcp"
