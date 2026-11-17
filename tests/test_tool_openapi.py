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
