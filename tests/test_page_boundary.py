import pytest
from unittest.mock import MagicMock, patch
from pydantic import ValidationError
from app.schemas import PageBoundaryProbe


def test_page_boundary_schema_validates():
    j = ('{"is_new_paper_header": true, "course_code": "ACC201", '
         '"session_hint": "exam", "has_question_one_reset": false}')
    out = PageBoundaryProbe.model_validate_json(j)
    assert out.is_new_paper_header is True
    assert out.course_code == "ACC201"
    assert out.session_hint == "exam"
    assert out.has_question_one_reset is False

def test_page_boundary_schema_defaults():
    out = PageBoundaryProbe.model_validate_json("{}")
    assert out.is_new_paper_header is False
    assert out.course_code is None
    assert out.session_hint is None
    assert out.has_question_one_reset is False

def test_page_boundary_rejects_bad_session():
    with pytest.raises(ValidationError):
        PageBoundaryProbe.model_validate_json('{"session_hint":"midterm"}')


def test_probe_page_boundary_uses_flash_and_thinking_off():
    """Decision B: the boundary probe is a CHEAP Flash call (thinking_budget=0, tiny cap, tiny
    schema) — not a full OCR. Mock the client like the OCR test and assert the config."""
    from app import llm

    fake = MagicMock()
    fake.text = '{"is_new_paper_header": true, "course_code": "ACC201", "session_hint": "CA"}'

    with patch.object(llm.client.models, "generate_content", return_value=fake) as mock_gen:
        out = llm.probe_page_boundary(b"img-bytes")

    assert isinstance(out, PageBoundaryProbe)
    assert out.course_code == "ACC201"
    assert mock_gen.call_count == 1
    kw = mock_gen.call_args.kwargs
    assert kw["model"] == llm.settings.model_flash, "boundary probe must use the Flash model"
    cfg = kw["config"]
    assert cfg.thinking_config is not None and cfg.thinking_config.thinking_budget == 0
    assert cfg.max_output_tokens <= 512, "boundary probe must keep a tiny token cap (not a full OCR)"
    assert cfg.response_schema is PageBoundaryProbe
