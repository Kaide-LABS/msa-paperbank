from app.db import Paper
from app.retrieval import find_paper


def test_retrieval(db_session):
    p1 = Paper(course_code="MTH102", semester="harmattan", year=2020, gcs_object="obj1", sha256="hash1", uploaded_by="test")
    p2 = Paper(course_code="MTH102", semester="rain", year=2021, gcs_object="obj2", sha256="hash2", uploaded_by="test")

    db_session.add_all([p1, p2])
    db_session.commit()

    found = find_paper(db_session, "MTH102", 2020, "harmattan")
    assert found is not None
    assert found.id == p1.id

    found_recent = find_paper(db_session, "MTH102", None, None)
    assert found_recent is not None
    assert found_recent.id == p2.id

    assert find_paper(db_session, "CSC101", None, None) is None