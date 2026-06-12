import pytest
from unittest.mock import MagicMock, patch
from app.schemas import OcrPaperExtraction
from pydantic import ValidationError

def test_ocr_schema_valid():
    json_str = '{"questions":[{"number":1,"text":"Solve dy/dx=2x"}]}'
    out = OcrPaperExtraction.model_validate_json(json_str)
    assert out.error is None
    assert len(out.questions) == 1
    assert out.questions[0].text == "Solve dy/dx=2x"

def test_ocr_schema_invalid_year():
    json_str = '{"exam_year":1990, "questions":[]}'
    with pytest.raises(ValidationError):
        OcrPaperExtraction.model_validate_json(json_str)

def test_ocr_schema_invalid_session():
    json_str = '{"exam_session":"fall", "questions":[]}'
    with pytest.raises(ValidationError):
        OcrPaperExtraction.model_validate_json(json_str)

def test_ocr_schema_error():
    json_str = '{"error":"image blank", "questions":[]}'
    out = OcrPaperExtraction.model_validate_json(json_str)
    assert out.error == "image blank"
    assert len(out.questions) == 0


def test_ocr_call_disables_thinking():
    """Decision 1 (BLOCKING BUG FIX): the OCR vision call MUST set thinking_budget=0.

    Probe finding: default thinking + max_output_tokens=4096 truncated every multi-page
    PDF (finish=MAX_TOKENS). This guards against a regression that would silently re-break
    multi-page ingest. Asserts the config passed to generate_content carries
    thinking_config.thinking_budget == 0.
    """
    from app import llm

    fake_resp = MagicMock()
    fake_resp.text = '{"questions":[{"number":1,"text":"x"}]}'

    with patch.object(llm.client.models, "generate_content", return_value=fake_resp) as mock_gen:
        out = llm.call_pro_vision([], "sys", OcrPaperExtraction)

    assert out == fake_resp.text
    assert mock_gen.call_count == 1
    cfg = mock_gen.call_args.kwargs["config"]
    assert cfg.thinking_config is not None, "OCR config must include ThinkingConfig"
    assert cfg.thinking_config.thinking_budget == 0, "OCR must run with thinking disabled"
    # Cap unchanged — the fix works at the existing 4096 budget.
    assert cfg.max_output_tokens == 4096


def test_router_call_does_not_set_thinking_budget_zero():
    """Decision 1 scope guard: ONLY the OCR call is modified. The router must be untouched
    (no thinking_budget=0 forced on it)."""
    from app import llm
    from app.schemas import RouterOutput

    fake_resp = MagicMock()
    fake_resp.text = '{"intent":"greeting","confidence":0.9}'
    fake_resp.usage_metadata = None

    with patch.object(llm.client.models, "generate_content", return_value=fake_resp) as mock_gen:
        llm.route("hi")

    cfg = mock_gen.call_args.kwargs["config"]
    budget = getattr(getattr(cfg, "thinking_config", None), "thinking_budget", None)
    assert budget != 0, "router config must not be forced to thinking_budget=0 (OCR-only change)"