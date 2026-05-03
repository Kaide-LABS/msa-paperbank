import pytest
from unittest.mock import patch
from app.pipeline import handle_message
from app.schemas import WAMessage, WAText, TextReply
from app.db import User, UserTombstone, RequestLog

@patch("app.pipeline.llm.route")
def test_opt_out_flow(mock_route, db_session):
    msg1 = WAMessage(id="msg_opt_out", from_="phone_opt", timestamp="1", type="text", text=WAText(body="STOP TRACKING"))
    
    reply1 = handle_message(db_session, msg1, None, None)
    assert isinstance(reply1, TextReply)
    assert "data is wiped" in reply1.body
    
    assert db_session.get(User, "phone_opt") is None
    assert db_session.get(UserTombstone, "phone_opt") is not None
    
    mock_route.assert_not_called()
    
    # 2nd msg, re-engage
    msg2 = WAMessage(id="msg_reengage", from_="phone_opt", timestamp="2", type="text", text=WAText(body="Hello"))
    
    from app.schemas import RouterOutput
    mock_route.return_value = (RouterOutput(intent="paper_request", course_code="MTH102", year=2020, confidence=0.9), 10, 10)
    
    handle_message(db_session, msg2, None, None)
    
    assert db_session.get(UserTombstone, "phone_opt") is None
    u = db_session.get(User, "phone_opt")
    assert u is not None