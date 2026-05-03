import pytest
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