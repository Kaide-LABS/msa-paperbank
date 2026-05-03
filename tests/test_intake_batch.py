import pytest
from unittest.mock import patch, MagicMock
from app.schemas import WAMessage, WAImage
from app.db import Uploader, ImageBatch, ImageBatchItem
from app.intake import handle_image

@pytest.fixture
def image_msg():
    from app.schemas import WAText
    return WAMessage(
        id="msg_img_123",
        from_="234800",
        timestamp="123",
        type="image",
        image=WAImage(id="media_123", mime_type="image/jpeg")
    )

@patch("app.whatsapp.get_media_metadata")
@patch("app.whatsapp.download_media")
def test_intake_batch_success(mock_download, mock_meta, db_session, image_msg):
    # Whitelist
    db_session.add(Uploader(phone_number="234800", added_by="test"))
    db_session.commit()
    
    mock_meta.return_value = ("http://dl", "image/jpeg", 1000)
    mock_download.return_value = b"test"
    
    mock_http = MagicMock()
    mock_gcs = MagicMock()
    
    reply = handle_image(db_session, mock_http, mock_gcs, image_msg)
    
    assert "got page 1" in reply.body
    
    from sqlalchemy import select
    batch = db_session.execute(select(ImageBatch).where(ImageBatch.phone_number == "234800")).scalar_one()
    assert batch.status == "open"
    
    items = db_session.execute(select(ImageBatchItem).where(ImageBatchItem.batch_id == batch.id)).scalars().all()
    assert len(items) == 1
    assert items[0].wa_media_id == "media_123"

@patch("app.whatsapp.get_media_metadata")
def test_intake_non_whitelisted(mock_meta, db_session, image_msg):
    # Not whitelisted
    mock_http = MagicMock()
    mock_gcs = MagicMock()
    
    reply = handle_image(db_session, mock_http, mock_gcs, image_msg)
    
    assert "isn't approved" in reply.body
    mock_meta.assert_not_called()

@patch("app.whatsapp.get_media_metadata")
def test_intake_rate_limit(mock_meta, db_session, image_msg):
    db_session.add(Uploader(phone_number="234800", added_by="test"))
    
    # 3 batches today already
    for i in range(3):
        db_session.add(ImageBatch(phone_number="234800"))
    db_session.commit()
    
    mock_http = MagicMock()
    mock_gcs = MagicMock()
    
    reply = handle_image(db_session, mock_http, mock_gcs, image_msg)
    
    assert "submitted enough today" in reply.body
    mock_meta.assert_not_called()