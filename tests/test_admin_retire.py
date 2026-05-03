import pytest
import sys
from unittest.mock import patch
from app.db import Paper
from admin.retire import main as retire_main

def test_admin_retire_success(db_session, monkeypatch):
    p = Paper(course_code="MTH102", semester="harmattan", year=2020, gcs_object="obj", sha256="h", uploaded_by="u")
    db_session.add(p)
    db_session.commit()

    test_args = ["admin.retire", str(p.id), "--reason", "Test reason", "--yes"]
    monkeypatch.setattr(sys, 'argv', test_args)
    
    retire_main()
    
    db_session.refresh(p)
    assert p.is_retired is True
    assert p.retired_reason == "Test reason"
    assert p.retired_by is not None
    assert p.retired_at is not None

def test_admin_retire_idempotent(db_session, monkeypatch):
    p = Paper(course_code="MTH102", semester="harmattan", year=2020, gcs_object="obj", sha256="h", uploaded_by="u", is_retired=True)
    db_session.add(p)
    db_session.commit()

    test_args = ["admin.retire", str(p.id), "--reason", "Test reason", "--yes"]
    monkeypatch.setattr(sys, 'argv', test_args)
    
    with pytest.raises(SystemExit) as e:
        retire_main()
    
    assert e.value.code == 0

def test_admin_retire_missing_reason(db_session, monkeypatch, capsys):
    p = Paper(course_code="MTH102", semester="harmattan", year=2020, gcs_object="obj", sha256="h", uploaded_by="u")
    db_session.add(p)
    db_session.commit()

    test_args = ["admin.retire", str(p.id), "--yes"]
    monkeypatch.setattr(sys, 'argv', test_args)
    
    with pytest.raises(SystemExit) as e:
        retire_main()
    
    assert e.value.code == 2