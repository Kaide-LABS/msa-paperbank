import pytest
import sys
from datetime import datetime, timezone
from sqlalchemy import select
from unittest.mock import patch, MagicMock
from app.db import PendingPaper, PendingPaperChunk, Paper, PaperChunk
from admin.curate import main as curate_main

def test_curate_promote(db_session, monkeypatch):
    pending = PendingPaper(
        course_code="MTH102",
        semester="harmattan",
        year=2020,
        gcs_object="obj",
        sha256="hash",
        uploaded_by="test"
    )
    db_session.add(pending)
    db_session.flush()
    
    c1 = PendingPaperChunk(pending_paper_id=pending.id, chunk_no=1, text="q1", embedding=[1.0]*768)
    db_session.add(c1)
    db_session.commit()
    
    # Mock builtins.input to return 'a' (approve), then 'reason', then 'q' (quit)
    inputs = ['a', 'good reason', 'q']
    def mock_input(prompt):
        return inputs.pop(0)
    monkeypatch.setattr('builtins.input', mock_input)
    
    with pytest.raises(SystemExit) as e:
        curate_main()
    assert e.value.code == 0
    
    db_session.refresh(pending)
    assert pending.review_status == 'approved'
    
    # Verify paper was promoted
    paper = db_session.execute(select(Paper).where(Paper.sha256 == "hash")).scalar_one()
    assert paper is not None
    assert paper.course_code == "MTH102"
    
    chunks = db_session.execute(select(PaperChunk).where(PaperChunk.paper_id == paper.id)).scalars().all()
    assert len(chunks) == 1
    assert chunks[0].text == "q1"

@patch('admin.curate.get_object_store')
def test_curate_reject(mock_get_object_store, db_session, monkeypatch):
    pending = PendingPaper(
        course_code="MTH102",
        semester="harmattan",
        year=2020,
        gcs_object="obj_to_delete",
        sha256="hash2",
        uploaded_by="test"
    )
    db_session.add(pending)
    db_session.commit()
    
    inputs = ['r', 'bad paper', 'q']
    def mock_input(prompt):
        return inputs.pop(0)
    monkeypatch.setattr('builtins.input', mock_input)
    
    mock_store = MagicMock()
    mock_get_object_store.return_value = mock_store

    with pytest.raises(SystemExit) as e:
        curate_main()
    assert e.value.code == 0

    db_session.refresh(pending)
    assert pending.review_status == 'rejected'

    # Verify paper was not promoted
    paper = db_session.execute(select(Paper).where(Paper.sha256 == "hash2")).scalar_one_or_none()
    assert paper is None

    # Verify the object-store delete was called
    mock_store.delete.assert_called_once_with("obj_to_delete")