import pytest
import os
import sys
from unittest.mock import MagicMock

# Mock missing heavy dependencies
sys.modules["cv2"] = MagicMock()
sys.modules["reportlab"] = MagicMock()
sys.modules["reportlab.pdfgen"] = MagicMock()
sys.modules["reportlab.pdfgen.canvas"] = MagicMock()
sys.modules["reportlab.lib"] = MagicMock()
sys.modules["reportlab.lib.pagesizes"] = MagicMock()

# Set dummy env vars before importing app
os.environ["GCP_PROJECT"] = "test-project"
os.environ["CLOUD_SQL_INSTANCE"] = "test:region:instance"
os.environ["DB_USER"] = "test-user"
os.environ["DB_PASSWORD"] = "test-pass"
os.environ["GCS_BUCKET"] = "test-bucket"
os.environ["WA_PHONE_NUMBER_ID"] = "test-pnid"
os.environ["WA_ACCESS_TOKEN"] = "test-token"
os.environ["WA_APP_SECRET"] = "test-secret"
os.environ["WA_VERIFY_TOKEN"] = "test-vtoken"

# Use sqlite for tests if no real DB provided
if not os.environ.get("DATABASE_URL_TEST"):
    os.environ["DATABASE_URL_TEST"] = "sqlite:///./test.db"

from sqlalchemy.orm import Session
from app.db import SessionLocal, Base, engine

@pytest.fixture(scope="session")
def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    from app.db import Course
    with SessionLocal() as session:
        # Check if MTH102 already exists (some engines might persist)
        from sqlalchemy import select
        existing = session.execute(select(Course).where(Course.code == "MTH102")).scalar()
        if not existing:
            session.add(Course(code="MTH102", title="General Math", level=100, department="Math"))
            session.commit()
        
    yield
    # We might want to keep the file if it's sqlite, or clean up
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def session(setup_database):
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

@pytest.fixture
def mock_http(mocker):
    return mocker.Mock()

@pytest.fixture
def mock_gcs(mocker):
    return mocker.Mock()