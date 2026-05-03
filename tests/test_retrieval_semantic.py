import pytest
import os
from datetime import datetime, timedelta
from app.db import Paper, PaperChunk
from app.retrieval import find_paper_by_semantic_query
from unittest.mock import patch

@pytest.fixture(autouse=True)
def check_vector_ext():
    if not os.environ.get("DATABASE_URL_TEST"):
        pytest.skip("DATABASE_URL_TEST not set")

def test_semantic_retrieval(db_session):
    # Skip if vector not installed
    try:
        db_session.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'").scalar()
    except Exception:
        pytest.xfail("pgvector not installed locally")

    p1 = Paper(course_code="MTH102", semester="harmattan", year=2021, gcs_object="obj1", sha256="h1", uploaded_by="u1")
    p2 = Paper(course_code="MTH102", semester="rain", year=2022, gcs_object="obj2", sha256="h2", uploaded_by="u1")
    
    # p3 is active risk but held_until is in the future
    p3 = Paper(course_code="MTH102", semester="harmattan", year=2026, gcs_object="obj3", sha256="h3", uploaded_by="u1", 
               is_active_risk=True, held_until=datetime.now() + timedelta(days=10))
    
    db_session.add_all([p1, p2, p3])
    db_session.commit()
    
    v1 = [1.0] + [0.0] * 767
    v2 = [0.0, 1.0] + [0.0] * 766
    v3 = [0.0, 0.0, 1.0] + [0.0] * 765
    
    c1 = PaperChunk(paper_id=p1.id, chunk_no=1, text="q1", embedding=v1)
    c2 = PaperChunk(paper_id=p2.id, chunk_no=1, text="q2", embedding=v2)
    c3 = PaperChunk(paper_id=p3.id, chunk_no=1, text="q3", embedding=v3)
    
    db_session.add_all([c1, c2, c3])
    db_session.commit()
    
    with patch("app.embeddings.embed_query") as mock_embed:
        # Query close to v2
        mock_embed.return_value = [0.1, 0.9] + [0.0] * 766
        
        found = find_paper_by_semantic_query(db_session, "MTH102", "some query")
        assert found is not None
        assert found.id == p2.id
        
        # Query close to v3 (but p3 is held)
        mock_embed.return_value = [0.0, 0.1, 0.9] + [0.0] * 765
        found_held = find_paper_by_semantic_query(db_session, "MTH102", "query")
        # should fallback to next best which is not held
        assert found_held is not None
        assert found_held.id != p3.id

        # Wrong course
        found_wrong = find_paper_by_semantic_query(db_session, "CSC101", "query")
        assert found_wrong is None