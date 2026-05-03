import pytest
from app.db import Paper
from app.retrieval import find_paper

def test_retrieval_multicourse(db_session):
    p = Paper(course_code="CSC305", semester="harmattan", year=2020, gcs_object="obj", sha256="hash", uploaded_by="u")
    db_session.add(p)
    db_session.commit()
    
    found = find_paper(db_session, "CSC305", 2020, "harmattan")
    assert found is not None
    assert found.id == p.id
    
    assert find_paper(db_session, "MTH102", 2020, "harmattan") is None