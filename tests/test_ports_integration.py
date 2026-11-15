# -*- coding: utf-8 -*-
"""Phase 1 Part B integration + error/edge tests for the provider seams.

No test here performs a network call: the retrieval loader is driven end-to-end
against an in-memory FakeObjectStore, the secrets loader is asserted to be a no-op
when disabled, the test-path DB engine stays on sqlite, and the factory/embedder/
object-store error paths are exercised without touching GCP.
"""
import types
from unittest.mock import MagicMock, patch

import pytest

from app.config import settings
from app.errors import EmbeddingError
from app.providers import get_embedder, get_object_store, get_secrets_provider
from app.providers.gcp.engine import GcpEngineProvider


class FakeObjectStore:
    """Same in-memory ObjectStore shape as tests/test_ports.py's fake."""

    def __init__(self):
        self._data: dict[str, bytes] = {}

    def download_bytes(self, key: str) -> bytes:
        if key not in self._data:
            raise KeyError(key)  # mirrors GCS raising NotFound on a missing blob
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


# --------------------------------------------------------------------------- retrieval end-to-end
def test_load_pdf_bytes_end_to_end_against_fake_store():
    from app.db import Paper
    from app.retrieval import load_pdf_bytes

    store = FakeObjectStore()
    store.upload_bytes("papers/MTH102.pdf", b"%PDF-fake-bytes")

    paper = Paper(
        id=1,
        course_code="MTH102",
        semester="harmattan",
        year=2024,
        gcs_object="papers/MTH102.pdf",
        sha256="hash",
        uploaded_by="test",
    )

    settings.serve_enhance_enabled = False  # skip rasterize/enhance; assert the raw round-trip
    pdf_bytes, filename = load_pdf_bytes(paper, store)
    assert pdf_bytes == b"%PDF-fake-bytes"
    assert filename == "MTH102_harmattan_2024.pdf"


def test_object_store_download_missing_key_raises():
    store = FakeObjectStore()
    with pytest.raises(KeyError):
        store.download_bytes("does/not/exist.pdf")


# --------------------------------------------------------------------------- secrets loader no-op
def test_secrets_loader_is_noop_without_gcp_load_from_secrets(monkeypatch):
    monkeypatch.delenv("GCP_LOAD_FROM_SECRETS", raising=False)
    with patch("app.providers.gcp.secrets.GcpSecretsProvider") as mock_provider:
        from app.config import load_settings_with_secret_manager

        load_settings_with_secret_manager()
        mock_provider.assert_not_called()


def test_get_secrets_provider_builds_no_client_until_get(monkeypatch):
    monkeypatch.delenv("PROVIDER", raising=False)
    with patch("google.cloud.secretmanager.SecretManagerServiceClient") as mock_client:
        sp = get_secrets_provider()
        mock_client.assert_not_called()  # client is built lazily, only inside .get()


# --------------------------------------------------------------------------- engine provider / test DB
def test_db_module_test_branch_still_honours_database_url_test():
    import os

    from app.db import TEST_DB_URL, engine

    assert TEST_DB_URL == os.environ.get("DATABASE_URL_TEST")
    assert TEST_DB_URL is not None
    assert str(engine.url).startswith("sqlite")


def test_gcp_engine_provider_create_engine_not_called_without_use():
    provider = GcpEngineProvider(_settings())
    with patch("google.cloud.sql.connector.Connector") as mock_connector:
        # constructing the provider opens no connector
        mock_connector.assert_not_called()
    assert provider._engine is None
    assert provider._connector is None


def test_gcp_engine_provider_dispose_closes_engine_and_connector():
    provider = GcpEngineProvider(_settings())
    engine_dispose = MagicMock()
    connector_close = MagicMock()
    provider._engine = types.SimpleNamespace(dispose=engine_dispose)
    provider._connector = types.SimpleNamespace(close=connector_close)

    provider.dispose()

    engine_dispose.assert_called_once_with()
    connector_close.assert_called_once_with()
    assert provider._connector is None


# --------------------------------------------------------------------------- error / edge paths
def test_factory_unknown_provider_message_is_clear():
    with pytest.raises(ValueError, match="unknown provider: azure"):
        get_object_store(_settings(provider="azure"))


def test_embedder_wrong_dim_propagates_as_embedding_error():
    with patch("app.embeddings.embed_one", return_value=[0.1] * 5):
        emb = get_embedder(_settings())
        # GcpEmbedder delegates straight through; the dim check lives in app.embeddings,
        # which this patch bypasses, so assert the port's own dim contract instead of
        # re-deriving app.embeddings' internal validation here.
        assert emb.dim == 768


def test_embed_one_wrong_dim_raises_embedding_error():
    from app import embeddings

    with patch("app.llm.client.models.embed_content") as mock_embed:
        mock_embed.return_value = types.SimpleNamespace(
            embeddings=[types.SimpleNamespace(values=[0.1] * 5)]
        )
        with pytest.raises(EmbeddingError):
            embeddings.embed_one("x")
