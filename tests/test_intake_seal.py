import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from sqlalchemy import select
from app.db import ImageBatch, ImageBatchItem, PendingPaper, IntakeNotification
from app.intake import sweep_and_seal
from app.config import settings

@patch("app.intake.ocr_paper")
@patch("app.intake.embed_many")
@patch("app.intake.stitch_images_to_pdf")
@patch("app.intake.prepare_images_for_ocr")
def test_intake_seal_success(mock_prepare, mock_stitch, mock_embed, mock_ocr, db_session):
    # Short seal window for test
    settings.image_batch_seal_seconds = 0
    
    batch = ImageBatch(phone_number="234800", last_item_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    db_session.add(batch)
    db_session.flush()
    
    item1 = ImageBatchItem(batch_id=batch.id, wa_media_id="m1", wa_message_id="msg1", gcs_object="gs://1", mime_type="image/jpeg", sha256="s1", ord=1)
    db_session.add(item1)
    db_session.commit()
    
    from app.schemas import OcrPaperExtraction, OcrQuestion
    mock_ocr.return_value = OcrPaperExtraction(course_code="MTH102", questions=[OcrQuestion(number=1, text="test")])
    mock_embed.return_value = [[0.0]*768]
    mock_stitch.return_value = b"pdf"
    # Decision 2: intake now sends raw bytes through prepare_images_for_ocr (preprocess off by default).
    mock_prepare.side_effect = lambda raw_list: list(raw_list)
    
    mock_gcs = MagicMock()
    
    # Must add MTH102 to known courses
    from app.db import Course
    db_session.add(Course(code="MTH102", title="Math", level=100, department="Math"))
    db_session.commit()
    
    sealed_count = sweep_and_seal(db_session, mock_gcs)
    assert sealed_count == 1
    
    db_session.refresh(batch)
    assert batch.status == "ocr_done"
    assert batch.pending_paper_id is not None
    
    pending = db_session.get(PendingPaper, batch.pending_paper_id)
    assert pending.source == "wa_intake"
    
    # Check notification
    notifs = db_session.execute(select(IntakeNotification).where(IntakeNotification.phone_number == "234800")).scalars().all()
    assert len(notifs) == 1
    assert "Submitted for review" in notifs[0].body

def test_intake_seal_empty_batch(db_session):
    settings.image_batch_seal_seconds = 0
    batch = ImageBatch(phone_number="234800", last_item_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    db_session.add(batch)
    db_session.commit()
    
    mock_gcs = MagicMock()
    sweep_and_seal(db_session, mock_gcs)
    
    db_session.refresh(batch)
    assert batch.status == "failed"
    assert batch.failure_reason == "empty"