from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.auth import require_tool_token
from app.deps import get_session
from app.main import PaperModel, RetrieveResponse, app
from app.retrieval import RetrievalResult

_MISSING = object()
SIGNED = "https://host/download?key=k&exp=1&sig=s"


class FakeStore:
    def signed_url(self, key):
        return SIGNED


@pytest.fixture
def client(monkeypatch):
    original_overrides = dict(app.dependency_overrides)
    original_store = getattr(app.state, "store", _MISSING)
    app.dependency_overrides[require_tool_token] = lambda: None
    app.dependency_overrides[get_session] = lambda: iter([None])
    app.state.store = FakeStore()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)
        if original_store is _MISSING:
            del app.state.store
        else:
            app.state.store = original_store


def _post(client):
    return client.post("/tool/retrieve", json={"query": "MTH102 2022"})


def _assert_declared(body):
    assert set(body) <= set(RetrieveResponse.model_fields)
    if body.get("paper") is not None:
        assert set(body["paper"]) <= set(PaperModel.model_fields)
    RetrieveResponse.model_validate(body, strict=True)


def test_found_body_is_exact(client, monkeypatch):
    paper = SimpleNamespace(
        id=7,
        course_code="MTH102",
        course_title="Calculus II",
        year=2022,
        semester="harmattan",
        exam_session="CA1",
        object_key="papers/MTH102/2022.pdf",
        served_object_key=None,
    )
    monkeypatch.setattr(
        "app.main.retrieval.answer_query",
        lambda *a, **k: RetrievalResult(paper=paper, intent="paper_request", course_code="MTH102"),
    )
    r = _post(client)
    assert r.status_code == 200
    assert r.json() == {
        "found": True,
        "intent": "paper_request",
        "paper": {
            "id": 7,
            "course_code": "MTH102",
            "course_title": "Calculus II",
            "year": 2022,
            "semester": "harmattan",
            "exam_session": "CA1",
        },
        "signed_url": SIGNED,
    }
    _assert_declared(r.json())


def test_not_found_body_is_exact(client, monkeypatch):
    monkeypatch.setattr(
        "app.main.retrieval.answer_query",
        lambda *a, **k: RetrievalResult(paper=None, intent="paper_request", course_code=None, course_known=False),
    )
    r = _post(client)
    assert r.status_code == 200
    assert r.json() == {
        "found": False,
        "intent": "paper_request",
        "course_code": None,
        "course_known": False,
    }
    _assert_declared(r.json())


def test_overrides_empty_after_fixture():
    assert app.dependency_overrides == {}
