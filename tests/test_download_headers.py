import pytest
from fastapi.testclient import TestClient

from app.main import _download_headers, app

_MISSING = object()


class FakeStore:
    def download_bytes(self, key):
        return b"%PDF-1.4 fake"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("app.main.signing.verify", lambda *a, **k: True)
    original = getattr(app.state, "store", _MISSING)
    app.state.store = FakeStore()
    try:
        yield TestClient(app)
    finally:
        if original is _MISSING:
            del app.state.store
        else:
            app.state.store = original


def _get(client, key):
    return client.get("/download", params={"key": key, "exp": 9999999999, "sig": "x"})


def test_pdf_key_is_application_pdf(client):
    r = _get(client, "papers/MTH102/2022.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content == b"%PDF-1.4 fake"


@pytest.mark.parametrize("key", ["papers/file.xyz", "papers/noext"])
def test_unknown_or_absent_extension_is_octet_stream(client, key):
    r = _get(client, key)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"


def test_content_disposition_inline_with_last_segment(client):
    r = _get(client, "papers/MTH102/2022.pdf")
    cd = r.headers["content-disposition"]
    assert cd.startswith("inline")
    assert 'filename="2022.pdf"' in cd


def test_key_without_slash_uses_whole_key(client):
    r = _get(client, "solo.pdf")
    assert 'filename="solo.pdf"' in r.headers["content-disposition"]


def test_non_ascii_and_control_characters_yield_printable_ascii_header(client):
    key = "papers/caf\u00e9 \U0001F600 \u201cq\u201d\x00\t\x7f.pdf"
    r = _get(client, key)
    assert r.status_code == 200
    cd = r.headers["content-disposition"]
    assert cd.startswith("inline")
    assert all(0x20 <= ord(c) <= 0x7E for c in cd)
    assert cd.endswith('.pdf"')


def test_trailing_slash_key_falls_back_to_download(client):
    r = _get(client, "papers/folder/")
    assert r.status_code == 200
    assert r.headers["content-disposition"] == 'inline; filename="download"'


def test_helper_is_pure():
    assert _download_headers("a/b/c.pdf") == ("application/pdf", 'inline; filename="c.pdf"')
    assert _download_headers("a\\b\\c.pdf") == ("application/pdf", 'inline; filename="c.pdf"')
    assert _download_headers("") == ("application/octet-stream", 'inline; filename="download"')
