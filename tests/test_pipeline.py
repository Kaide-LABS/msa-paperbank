import pytest
from unittest.mock import patch
from app.pipeline import handle_message
from app.schemas import WAMessage, TextReply, DocumentReply, WAText
from app.db import RequestLog, Paper
from app.errors import DuplicateMessage

@pytest.fixture
def base_msg():
    return WAMessage(
        id="msg123",
        from_="2348000000000",
        timestamp="1234567890",
        type="text",
        text=WAText(body="Hello")
    )

@patch("app.pipeline.llm.route")
def test_pipeline_duplicate(mock_route, db_session, base_msg):
    from app.schemas import RouterOutput
    mock_route.return_value = (RouterOutput(intent="greeting", confidence=0.9), 10, 10)
    handle_message(db_session, base_msg)
    with pytest.raises(DuplicateMessage):
        handle_message(db_session, base_msg)

def test_pipeline_non_text(db_session, base_msg):
    base_msg.type = "image"
    base_msg.id = "msg_img"
    base_msg.text = None
    reply = handle_message(db_session, base_msg)
    assert isinstance(reply, TextReply)
    assert "Send the course code" in reply.body

@patch("app.pipeline.llm.route")
def test_pipeline_greeting(mock_route, db_session, base_msg):
    base_msg.id = "msg_greet"
    from app.schemas import RouterOutput
    mock_route.return_value = (RouterOutput(intent="greeting", confidence=0.9), 10, 10)
    reply = handle_message(db_session, base_msg)
    assert isinstance(reply, TextReply)
    assert "Wa alaykum salaam" in reply.body

@patch("app.pipeline.llm.route")
def test_pipeline_found(mock_route, db_session, base_msg):
    # Setup paper
    p = Paper(course_code="MTH102", semester="harmattan", year=2020, gcs_object="obj1", sha256="hash1", uploaded_by="test")
    db_session.add(p)
    db_session.commit()
    
    base_msg.id = "msg_found"
    from app.schemas import RouterOutput
    mock_route.return_value = (RouterOutput(intent="paper_request", course_code="MTH102", year=2020, semester="harmattan", confidence=0.9), 10, 10)
    
    reply = handle_message(db_session, base_msg)
    assert isinstance(reply, DocumentReply)
    assert reply.paper_id == p.id

@patch("app.pipeline.llm.route")
def test_pipeline_unknown_course_returns_suggestions(mock_route, db_session, base_msg):
    from app.db import Course
    db_session.add_all([
        Course(code="MTH102", title="A", level=100, department="D"),
        Course(code="MTH101", title="A", level=100, department="D"),
        Course(code="MTH202", title="A", level=200, department="D")
    ])
    db_session.commit()
    
    base_msg.id = "msg_unknown_course"
    from app.schemas import RouterOutput
    mock_route.return_value = (RouterOutput(intent="paper_request", course_code="MTH999", year=2020, confidence=0.9), 10, 10)
    
    reply = handle_message(db_session, base_msg)
    assert isinstance(reply, TextReply)
    assert "Did you mean:" in reply.body
    assert "MTH102" in reply.body
    
@patch("app.pipeline.llm.route")
def test_pipeline_known_course_passes_to_retrieval(mock_route, db_session, base_msg):
    from app.db import Course
    db_session.add(Course(code="CSC305", title="A", level=300, department="D"))
    p = Paper(course_code="CSC305", semester="harmattan", year=2020, gcs_object="obj", sha256="hash", uploaded_by="u")
    db_session.add(p)
    db_session.commit()
    
    base_msg.id = "msg_known_course"
    from app.schemas import RouterOutput
    mock_route.return_value = (RouterOutput(intent="paper_request", course_code="CSC305", year=2020, semester="harmattan", confidence=0.9), 10, 10)
    
    reply = handle_message(db_session, base_msg)
    assert isinstance(reply, DocumentReply)
    assert reply.paper_id == p.id

@patch("app.pipeline.llm.route")
@patch("app.pipeline.retrieval.find_paper")
@patch("app.pipeline.retrieval.find_paper_by_semantic_query")
def test_pipeline_semantic_fallback_when_ilike_misses(mock_semantic, mock_find, mock_route, db_session, base_msg):
    # Setup paper
    p = Paper(course_code="MTH102", semester="harmattan", year=2020, gcs_object="obj1", sha256="hash1", uploaded_by="test")
    db_session.add(p)
    db_session.commit()
    
    base_msg.id = "msg_semantic"
    from app.schemas import RouterOutput
    mock_route.return_value = (RouterOutput(intent="paper_request", course_code="MTH102", year=None, confidence=0.8), 10, 10)
    mock_find.return_value = None
    mock_semantic.return_value = p
    
    reply = handle_message(db_session, base_msg)
    assert isinstance(reply, DocumentReply)
    assert reply.paper_id == p.id

@patch("app.pipeline.llm.route")
def test_pipeline_daily_token_budget_blocks(mock_route, db_session, base_msg):
    # Insert rows exceeding budget
    from app.config import settings
    
    for i in range(50):
        log_entry = RequestLog(
            wa_message_id=f"budget_msg_{i}",
            wa_from="2348000000000",
            user_text="test",
            outcome="sent",
            flash_input_tokens=(settings.daily_token_budget // 50) + 10,
            flash_output_tokens=10
        )
        db_session.add(log_entry)
    db_session.commit()

    base_msg.id = "msg_budget_exceeded"
    from app.schemas import RouterOutput
    mock_route.return_value = (RouterOutput(intent="paper_request", course_code="MTH102", year=2020, confidence=0.9), 10, 10)
    
    reply = handle_message(db_session, base_msg)
    assert isinstance(reply, TextReply)
    assert "daily limit" in reply.body
    
    # Check the log entry outcome
    from sqlalchemy import select
    log_check = db_session.execute(select(RequestLog).where(RequestLog.wa_message_id == "msg_budget_exceeded")).scalar_one()
    assert log_check.outcome == "rate_limited"
    assert log_check.error == "daily_token_budget_exceeded"