import pytest
import sys
from unittest.mock import patch
from app.db import Uploader
from app.intake import is_whitelisted
from admin.uploaders import main as uploaders_main

def test_uploaders_allow(db_session, monkeypatch):
    test_args = ["admin.uploaders", "allow", "234800", "--name", "Test"]
    monkeypatch.setattr(sys, 'argv', test_args)
    
    uploaders_main()
    
    u = db_session.get(Uploader, "234800")
    assert u is not None
    assert u.revoked_at is None
    
    assert is_whitelisted(db_session, "234800") is True

def test_uploaders_revoke(db_session, monkeypatch):
    u = Uploader(phone_number="234801", added_by="test")
    db_session.add(u)
    db_session.commit()
    
    test_args = ["admin.uploaders", "revoke", "234801", "--reason", "spam", "--yes"]
    monkeypatch.setattr(sys, 'argv', test_args)
    
    uploaders_main()
    
    db_session.refresh(u)
    assert u.revoked_at is not None
    assert u.revoke_reason == "spam"
    
    assert is_whitelisted(db_session, "234801") is False

def test_uploaders_re_allow(db_session, monkeypatch):
    # Already revoked
    u = Uploader(phone_number="234802", added_by="test", revoked_at=func.now())
    db_session.add(u)
    db_session.commit()
    
    test_args = ["admin.uploaders", "allow", "234802"]
    monkeypatch.setattr(sys, 'argv', test_args)
    
    uploaders_main()
    
    db_session.refresh(u)
    assert u.revoked_at is None
    assert is_whitelisted(db_session, "234802") is True