import pytest
import os
from unittest.mock import patch
from app.db import Paper, PaperChunk
from app.retrieval import find_paper, find_paper_by_semantic_query

@pytest.fixture(autouse=True)
def check_vector_ext():
    if not os.environ.get("DATABASE_URL_TEST"):
        pytest.skip("DATABASE_URL_TEST not set")

def test_retrieval_ignores_retired(db_session):
    try:
        db_session.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'").scalar()
    except Exception:
        pytest.xfail("pgvector not installed locally")

    p1 = Paper(course_code="MTH102", semester="harmattan", year=2021, gcs_object="obj1", sha256="h1", uploaded_by="u1", is_retired=True)
    p2 = Paper(course_code="MTH102", semester="rain", year=2021, gcs_object="obj2", sha256="h2", uploaded_by="u1", is_retired=False)
    
    db_session.add_all([p1, p2])
    db_session.commit()
    
    # Direct match for retired should return None
    assert find_paper(db_session, "MTH102", 2021, "harmattan") is None
    
    # Missing year returns most recent non-retired
    found = find_paper(db_session, "MTH102", None, None)
    assert found is not None
    assert found.id == p2.id
    
    # Semantic retrieval test
    v1 = [1.0] + [0.0] * 767
    v2 = [0.0, 1.0] + [0.0] * 766
    
    c1 = PaperChunk(paper_id=p1.id, chunk_no=1, text="q1", embedding=v1)
    c2 = PaperChunk(paper_id=p2.id, chunk_no=1, text="q2", embedding=v2)
    db_session.add_all([c1, c2])
    db_session.commit()

    with patch("app.embeddings.embed_query") as mock_embed:
        # Query close to retired paper (v1)
        mock_embed.return_value = [0.9, 0.1] + [0.0] * 766
        found_sem = find_paper_by_semantic_query(db_session, "MTH102", "query")
        
        # Should fallback to non-retired (p2)
        assert found_sem is not None
        assert found_sem.id == p2.id