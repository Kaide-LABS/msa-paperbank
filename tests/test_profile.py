import pytest
from app import profile
from app.db import User, UserTombstone

def test_is_opt_out_message():
    assert profile.is_opt_out_message("OPT OUT") is True
    assert profile.is_opt_out_message("opt out") is True
    assert profile.is_opt_out_message("STOP TRACKING") is True
    assert profile.is_opt_out_message("random") is False
    assert profile.is_opt_out_message("OPTOUT") is False

def test_record_interaction_increments_count(db_session):
    profile.record_interaction(db_session, "123", "MTH102")
    user = db_session.get(User, "123")
    assert user is not None
    assert user.interaction_count == 1
    assert user.inferred_courses == {"MTH102": 1}
    
    profile.record_interaction(db_session, "123", "MTH102")
    db_session.refresh(user)
    assert user.interaction_count == 2
    assert user.inferred_courses == {"MTH102": 2}
    
    profile.record_interaction(db_session, "123", "CSC305")
    db_session.refresh(user)
    assert user.interaction_count == 3
    assert user.inferred_courses == {"MTH102": 2, "CSC305": 1}
    
    profile.record_interaction(db_session, "123", None)
    db_session.refresh(user)
    assert user.interaction_count == 3

def test_get_top_courses(db_session):
    profile.record_interaction(db_session, "123", "A")
    profile.record_interaction(db_session, "123", "B")
    profile.record_interaction(db_session, "123", "B")
    
    top = profile.get_top_courses(db_session, "123", 2)
    assert top == ["B", "A"]

def test_tombstone_roundtrip(db_session):
    profile.ensure_user(db_session, "123")
    assert db_session.get(User, "123") is not None
    
    profile.opt_out(db_session, "123", "OPT OUT")
    assert db_session.get(User, "123") is None
    assert profile.is_tombstoned(db_session, "123") is True
    
    profile.clear_tombstone(db_session, "123")
    assert profile.is_tombstoned(db_session, "123") is False