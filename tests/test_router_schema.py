import pytest
from app.schemas import RouterOutput
from pydantic import ValidationError

def test_router_schema():
    valid_json = '{"intent":"paper_request","course_code":"MTH102","year":2022,"semester":"harmattan","confidence":0.95}'
    out = RouterOutput.model_validate_json(valid_json)
    assert out.intent == "paper_request"
    assert out.year == 2022
    
    with pytest.raises(ValidationError):
        RouterOutput.model_validate_json('{"intent":"paper_request","year":1999,"confidence":0.9}')
        
    with pytest.raises(ValidationError):
        RouterOutput.model_validate_json('{"intent":"paper_request","semester":"fall","confidence":0.9}')