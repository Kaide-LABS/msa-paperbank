import pytest
from fastapi.testclient import TestClient

from app.main import app

_MISSING = object()


class FakeStore:
    def __init__(self, missing=False):
        self.missing = missing

    def download_bytes(self, key):
        if self.missing:
            raise FileNotFoundError(key)
        return b"%PDF-1.4 fake"


@pytest.fixture
def make_client(monkeypatch):
    original = getattr(app.state, "store", _MISSING)

    def _make(verify=True, missing=False):
        monkeypatch.setattr("app.main.signing.verify", lambda *a, **k: verify)
        app.state.store = FakeStore(missing=missing)
        return TestClient(app)

    try:
        yield _make
    finally:
        if original is _MISSING:
            if hasattr(app.state, "store"):
                del app.state.store
        else:
            app.state.store = original


def _get(client, key):
    return client.get("/download", params={"key": key, "exp": 9999999999, "sig": "x"})


@pytest.mark.parametrize(
    "key",
    [
        'papers/we"ird.pdf',
        "papers/line\r\nbreak.pdf",
        "papers/back\\slash.pdf",
        'papers/a"b\\c\r\nd.pdf',
        "papers/../../etc/passwd",
        'papers/x";\r\nSet-Cookie: a=b.pdf',
    ],
)
def test_adversarial_filename_cannot_break_header(make_client, key):
    r = _get(make_client(), key)
    assert r.status_code == 200
    cd = r.headers["content-disposition"]
    assert cd.startswith('inline; filename="') and cd.endswith('"')
    name = cd[len('inline; filename="'):-1]
    for bad in ('"', "\r", "\n", "\\", "/"):
        assert bad not in name
    assert "Set-Cookie" not in r.headers


def test_invalid_signature_is_403(make_client):
    r = _get(make_client(verify=False), "papers/a.pdf")
    assert r.status_code == 403
    assert "content-disposition" not in r.headers


def test_missing_object_is_404(make_client):
    r = _get(make_client(missing=True), "papers/a.pdf")
    assert r.status_code == 404
    assert "content-disposition" not in r.headers
