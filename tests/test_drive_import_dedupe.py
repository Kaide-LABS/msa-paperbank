import pytest
import sys
from unittest.mock import patch, MagicMock
from app.db import PendingPaper
from sqlalchemy import select
from scripts.drive_import import main as drive_main

@patch("scripts.drive_import.get_drive_service")
def test_drive_import_dedupe(mock_drive, db_session, monkeypatch, capsys):
    mock_service = MagicMock()
    mock_drive.return_value = mock_service
    
    # Return 3 files: 2 duplicates, 1 unparseable
    mock_service.files().list().execute.return_value = {
        'files': [
            {'id': '1', 'name': 'MTH102-EXAM-2020-q1.jpg', 'mimeType': 'image/jpeg'},
            {'id': '2', 'name': 'MTH102-EXAM-2020-q2.jpg', 'mimeType': 'image/jpeg'},
            {'id': '3', 'name': 'unparseable.pdf', 'mimeType': 'application/pdf'}
        ]
    }
    
    # Mock media download
    mock_media = MagicMock()
    mock_media.execute.return_value = b"test_content"
    mock_service.files().get_media.return_value = mock_media
    
    test_args = ["scripts.drive_import", "--folder", "test_folder", "--dry-run"]
    monkeypatch.setattr(sys, 'argv', test_args)
    
    # Mock settings so we can import without issues
    with patch("scripts.drive_import.settings") as mock_settings:
        mock_settings.gcp_project = "test"
        mock_settings.gcs_bucket = "test_bucket"
        
        drive_main()
    
    captured = capsys.readouterr()
    assert "unparsed_filename: unparseable.pdf" in captured.out
    assert "Would ingest: course=MTH102, year=2020, session=EXAM, files=2" in captured.out