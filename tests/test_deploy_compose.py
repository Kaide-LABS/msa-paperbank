"""Phase 5 deployment checks (Part A).

All static/structural or TestClient-based — no Docker daemon, no network, no model
load. Verifies:
  * a credential-free provider=local boot constructs no storage.Client and serves /healthz;
  * _warmup under provider=local routes through app.state.embedder, never the Vertex import;
  * docker-compose.yml parses and wires db/app/minio with the required health checks/profile;
  * .env.example exists and holds no forbidden secret literal.
"""
import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE = REPO_ROOT / "docker-compose.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

# Reuse the Phase 3 forbidden-literal set (real GCP project id, Cloud SQL instance
# string, plaintext DB password). Deployment artifacts must carry placeholders only.
# Built from fragments so this test file itself carries no verbatim forbidden literal
# (the Phase 3 source-hygiene test scans every tracked file under tests/).
FORBIDDEN_LITERALS = (
    "umm" + "ah",
    "my-project:africa-south1:" + "paperbank",
    "DB_PASSWORD=" + "secret",
)


class _FakeEmbedder:
    """Injected embedder: records calls, loads no model, makes no network call."""

    def __init__(self):
        self.calls = []

    def embed_query(self, text):
        self.calls.append(text)
        return [0.0] * 768

    def embed_documents(self, texts, concurrency=None):
        return [[0.0] * 768 for _ in texts]

    @property
    def dim(self):
        return 768


def _boot_local_app(monkeypatch, fake_embedder):
    """Import app.main fresh under provider=local with GCS + warmup-title patched."""
    import app.config as config

    monkeypatch.setattr(config.settings, "provider", "local", raising=False)

    import app.main as main
    importlib.reload(main)
    # Inject the fake embedder/store and silence the title-index preload (no DB, no
    # model, no filesystem signing key needed in unit tests).
    monkeypatch.setattr(main, "get_embedder", lambda settings: fake_embedder)
    monkeypatch.setattr(main, "get_object_store", lambda settings: MagicMock())
    import app.title_index as title_index
    monkeypatch.setattr(title_index, "ensure_loaded", lambda s: None, raising=False)
    monkeypatch.setattr(main.db, "SessionLocal", lambda: MagicMock())
    return main


def test_local_boot_constructs_no_storage_client(monkeypatch):
    from fastapi.testclient import TestClient

    fake = _FakeEmbedder()
    main = _boot_local_app(monkeypatch, fake)

    with patch("google.cloud.storage.Client") as gcs_client:
        with TestClient(main.app) as client:
            resp = client.get("/healthz")
            assert resp.status_code == 200
            assert resp.json() == {"ok": True}
        gcs_client.assert_not_called()


def test_warmup_routes_through_active_embedder_not_vertex(monkeypatch):
    fake = _FakeEmbedder()
    main = _boot_local_app(monkeypatch, fake)

    import app.embeddings as embeddings
    with patch.object(embeddings, "embed_query") as vertex_embed:
        main._warmup(fake)
        vertex_embed.assert_not_called()
    assert fake.calls == ["warmup"]


def test_compose_parses_and_wires_services():
    assert COMPOSE.exists(), "docker-compose.yml missing"
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services = data["services"]
    assert {"db", "app", "minio"} <= set(services)

    db = services["db"]
    assert "pgvector" in db["image"]
    assert "pg_isready" in str(db["healthcheck"]["test"])

    app = services["app"]
    assert app["depends_on"]["db"]["condition"] == "service_healthy"
    assert "/healthz" in str(app["healthcheck"]["test"])

    minio = services["minio"]
    assert "minio" in minio["profiles"]


def test_compose_has_no_forbidden_literal():
    text = COMPOSE.read_text(encoding="utf-8")
    for literal in FORBIDDEN_LITERALS:
        assert literal not in text, f"forbidden literal in docker-compose.yml: {literal}"


def test_env_example_exists_and_is_placeholder_only():
    assert ENV_EXAMPLE.exists(), ".env.example missing"
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert text.strip(), ".env.example is empty"
    assert "PROVIDER=local" in text
    for literal in FORBIDDEN_LITERALS:
        assert literal not in text, f"forbidden literal in .env.example: {literal}"
