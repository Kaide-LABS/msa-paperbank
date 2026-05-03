import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from app.db import RequestLog
from app.config import settings
from app import pipeline
from app.schemas import WAMessage, TextReply, DocumentReply

def test_cost_breaker_trips(session, mock_http, mock_gcs):
    # 1. Seed enough cost to trip the breaker ($0.50 cap)
    # 1,000,000 input tokens at $0.50/1M = $0.50
    log = RequestLog(
        wa_message_id="prev_msg",
        wa_from="2348000000000",
        user_text="expensive request",
        outcome="sent",
        flash_input_tokens=1_000_000,
        flash_output_tokens=0,
        received_at=datetime.now(timezone.utc) - timedelta(minutes=5)
    )
    session.add(log)
    session.commit()
    
    # 2. Set cap to 0.40 (already exceeded)
    settings.daily_cost_usd_cap = 0.40
    
    msg = WAMessage(
        id="new_msg",
        from_="2348000000000",
        timestamp="123456789",
        type="text",
        text={"body": "MTH102"}
    )
    
    reply = pipeline.handle_message(session, msg, mock_http, mock_gcs)
    
    assert isinstance(reply, TextReply)
    assert "daily limit" in reply.body.lower()
    
    # Verify DB state
    new_log = session.execute(select(RequestLog).where(RequestLog.wa_message_id == "new_msg")).scalar_one()
    assert new_log.outcome == "rate_limited"
    assert new_log.error == "daily_cost_cap_exceeded"

def test_cost_breaker_allows_under_cap(session, mock_http, mock_gcs, monkeypatch):
    # 1. Seed some cost under the cap
    log = RequestLog(
        wa_message_id="prev_msg",
        wa_from="2348000000000",
        user_text="cheap request",
        outcome="sent",
        flash_input_tokens=100,
        flash_output_tokens=100,
        received_at=datetime.now(timezone.utc) - timedelta(minutes=5)
    )
    session.add(log)
    session.commit()
    
    settings.daily_cost_usd_cap = 0.50
    
    # Mock LLM route to avoid real API call
    from app.schemas import RouterOutput
    def mock_route(text):
        return RouterOutput(intent="greeting", confidence=1.0), 10, 10
    monkeypatch.setattr("app.llm.route", mock_route)
    
    msg = WAMessage(
        id="new_msg",
        from_="2348000000000",
        timestamp="123456789",
        type="text",
        text={"body": "hi"}
    )
    
    reply = pipeline.handle_message(session, msg, mock_http, mock_gcs)
    assert isinstance(reply, TextReply)
    assert "Wa alaykum salaam" in reply.body
