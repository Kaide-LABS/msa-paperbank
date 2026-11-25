import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def spec():
    return TestClient(app).get("/openapi.json").json()


def _resolve(spec, schema):
    ref = schema.get("$ref")
    if ref:
        node = spec
        for part in ref.lstrip("#/").split("/"):
            node = node[part]
        return node
    return schema


def test_operation_id_is_retrieve_paper(spec):
    op = spec["paths"]["/tool/retrieve"]["post"]
    assert op["operationId"] == "RetrievePaper"
    assert op["summary"]
    assert op["description"]


def test_request_fields_have_descriptions(spec):
    op = spec["paths"]["/tool/retrieve"]["post"]
    schema = _resolve(spec, op["requestBody"]["content"]["application/json"]["schema"])
    for field in ("query", "prefer_courses"):
        assert schema["properties"][field].get("description"), field


def _response_schema(spec):
    op = spec["paths"]["/tool/retrieve"]["post"]
    return _resolve(spec, op["responses"]["200"]["content"]["application/json"]["schema"])


def test_response_fields_have_descriptions(spec):
    schema = _response_schema(spec)
    props = schema["properties"]
    for field in ("found", "intent", "course_code", "course_known", "paper", "signed_url"):
        assert props[field].get("description"), field


def test_signed_url_mentions_fifteen_minutes(spec):
    desc = _response_schema(spec)["properties"]["signed_url"]["description"]
    assert "15 minutes" in desc


def test_paper_fields_have_descriptions(spec):
    paper_prop = _response_schema(spec)["properties"]["paper"]
    options = paper_prop.get("anyOf") or [paper_prop]
    paper_schema = None
    for option in options:
        resolved = _resolve(spec, option)
        if "properties" in resolved:
            paper_schema = resolved
    assert paper_schema is not None
    for field in ("id", "course_code", "course_title", "year", "semester", "exam_session"):
        assert paper_schema["properties"][field].get("description"), field


def test_401_is_documented(spec):
    responses = spec["paths"]["/tool/retrieve"]["post"]["responses"]
    assert "401" in responses
    assert responses["401"]["description"]

