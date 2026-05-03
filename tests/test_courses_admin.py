import pytest
import sys
from unittest.mock import patch
from app.db import Course
from admin.courses import main as courses_main

def test_courses_admin_add(db_session, monkeypatch):
    test_args = ["admin.courses", "add", "CSC305", "--title", "Algorithms", "--level", "300", "--department", "Computer Science"]
    monkeypatch.setattr(sys, 'argv', test_args)
    
    courses_main()
    
    c = db_session.get(Course, "CSC305")
    assert c is not None
    assert c.title == "Algorithms"
    assert c.is_active is True

def test_courses_admin_add_duplicate(db_session, monkeypatch):
    c = Course(code="CSC305", title="Alg", level=300, department="CS")
    db_session.add(c)
    db_session.commit()
    
    test_args = ["admin.courses", "add", "CSC305", "--title", "Alg2", "--level", "300", "--department", "CS"]
    monkeypatch.setattr(sys, 'argv', test_args)
    
    with pytest.raises(SystemExit) as e:
        courses_main()
    
    assert e.value.code == 1

def test_courses_admin_deactivate(db_session, monkeypatch):
    c = Course(code="CSC305", title="Alg", level=300, department="CS")
    db_session.add(c)
    db_session.commit()
    
    test_args = ["admin.courses", "deactivate", "CSC305", "--yes"]
    monkeypatch.setattr(sys, 'argv', test_args)
    
    courses_main()
    
    db_session.refresh(c)
    assert c.is_active is False