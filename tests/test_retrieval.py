from app.db import Paper
from app.retrieval import find_paper
from datetime import datetime

def test_retrieval(db_session):
    # Setup some papers
    p1 = Paper(course_code="MTH102", semester="harmattan", year=2020, gcs_object="obj1", sha256="hash1", uploaded_by="test")
    p2 = Paper(course_code="MTH102", semester="rain", year=2021, gcs_object="obj2", sha256="hash2", uploaded_by="test")
    current_year = datetime.now().year
    p3 = Paper(course_code="MTH102", semester="harmattan", year=current_year, gcs_object="obj3", sha256="hash3", uploaded_by="test", is_quarantined=True)
    
    db_session.add_all([p1, p2, p3])
    db_session.commit()
    
    # Exact match
    found = find_paper(db_session, "MTH102", 2020, "harmattan")
    assert found is not None
    assert found.id == p1.id
    
    # Missing year returns most recent (but not quarantined)
    found_recent = find_paper(db_session, "MTH102", None, None)
    assert found_recent is not None
    assert found_recent.id == p2.id
    
    # Wrong course returns None
    assert find_paper(db_session, "CSC101", None, None) is None
    
    # Quarantined paper cannot be retrieved
    assert find_paper(db_session, "MTH102", current_year, "harmattan") is None