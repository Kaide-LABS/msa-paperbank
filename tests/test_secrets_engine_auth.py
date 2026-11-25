import subprocess

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth import require_tool_token
from app.ports import EngineProvider
from app.providers.local.engine import PostgresEngineProvider
from app.providers.local.secrets import EnvSecretsProvider, FileSecretsProvider


def test_tracked_sources_contain_no_gcp_secret_literals():
    """Keep removed deployment credentials from returning in tracked sources."""
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z"], text=False
    ).decode().split("\0")
    source_roots = ("app/", "admin/", "cloud_ingest/", "scripts/", "tests/", "migrations/")
    forbidden = (
        "ummah",
        "my-project:africa-south1:paperbank",
        "DB_PASSWORD=secret",
    )
    violations = []
    for name in tracked:
        if not name or not name.startswith(source_roots) or name == "tests/test_secrets_engine_auth.py":
            continue
        try:
            contents = open(name, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        for literal in forbidden:
            if literal in contents:
                violations.append(f"{name}: {literal}")
    assert not violations, "forbidden deployment literals found: " + ", ".join(violations)


def test_env_secret(monkeypatch):
    monkeypatch.setenv("DEMO_SECRET", "value")
    assert EnvSecretsProvider().get("DEMO_SECRET") == "value"
    with pytest.raises(RuntimeError):
        EnvSecretsProvider().get("MISSING_DEMO_SECRET")


def test_file_secret(tmp_path):
    (tmp_path / "demo").write_text("value\n", encoding="utf-8")
    provider = FileSecretsProvider(tmp_path)
    assert provider.get("demo") == "value"
    with pytest.raises(RuntimeError):
        provider.get("missing")


def test_postgres_engine_is_lazy_and_implements_port():
    provider = PostgresEngineProvider(type("S", (), {"database_url": "postgresql://u:p@localhost/db"})())
    assert isinstance(provider, EngineProvider)
    engine = provider.create_engine()
    assert str(engine.url) == "postgresql+pg8000://u:***@localhost/db"
    provider.dispose()


def test_tool_auth_fail_closed(monkeypatch):
    monkeypatch.setattr("app.config.settings.tool_api_token", "secret")
    app = FastAPI()

    @app.get("/private")
    def private(_: None = Depends(require_tool_token)):
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/private").status_code == 401
    assert client.get("/private", headers={"Authorization": "Basic secret"}).status_code == 401
    assert client.get("/private", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/private", headers={"Authorization": "Bearer secret"}).json() == {"ok": True}
