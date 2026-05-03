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
def test_pipeline_not_found(mock_route, db_session, base_msg):
    base_msg.id = "msg_notfound"
    from app.schemas import RouterOutput
    mock_route.return_value = (RouterOutput(intent="paper_request", course_code="MTH102", year=1990, confidence=0.9), 10, 10)
    
    reply = handle_message(db_session, base_msg)
    assert isinstance(reply, TextReply)
    assert "We don't have this MTH102 paper yet" in reply.body

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